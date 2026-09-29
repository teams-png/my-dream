from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import User
from .serializers import RegisterSerializer, MeSerializer
from . import services


class RegisterView(generics.CreateAPIView):
    """
    Creates the platform User only. Creating their first Company (and
    becoming its Owner) is a separate step — see tenants.services.create_company_with_owner —
    kept distinct because an accountant User might later join an existing
    company instead of creating their own (Phase 0/1 Section 6).
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class SecureTokenObtainPairView(TokenObtainPairView):
    """
    Wraps simplejwt's login with the lockout check from Phase 1 Section 27
    ("Login attempt protection") and records every attempt — success or
    failure — for the LoginAttempt ledger. `throttle_scope = "login"` also
    caps raw request *rate* (Section 27's "Rate limiting"), which is a
    separate, cheaper defense than the lockout (rate limiting slows a
    single fast attacker; lockout stops slow/distributed guessing against
    one account).
    """
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        identifier = request.data.get("username") or request.data.get("email") or ""
        ip_address = services.client_ip(request)

        if identifier and services.is_locked_out(identifier, ip_address):
            return Response(
                {"detail": "Too many failed login attempts. Try again later."},
                status=status.HTTP_423_LOCKED,
            )

        serializer = self.get_serializer(data=request.data)
        try:
            try:
                serializer.is_valid(raise_exception=True)
            except TokenError as exc:
                raise InvalidToken(exc.args[0])
        except AuthenticationFailed:
            if identifier:
                services.record_attempt(identifier, ip_address, successful=False)
            raise

        from . import twofactor
        user = getattr(serializer, "user", None)
        if user is not None and twofactor.is_enabled(user) and not twofactor.verify(user, request.data.get("otp", "")):
            if identifier:
                services.record_attempt(identifier, ip_address, successful=False)
            return Response(
                {"detail": "Two-factor code required. Send the authenticator code as 'otp'.", "two_factor_required": True},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        if identifier:
            services.record_attempt(identifier, ip_address, successful=(response.status_code == 200))

        return response
