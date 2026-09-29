from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class KitchenConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def resolve_company_id(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return None
        company_id = self.scope["session"].get("active_company_id")
        memberships = user.memberships.filter(is_active=True, company__is_active=True)
        membership = memberships.filter(company_id=company_id).first() if company_id else memberships.first()
        return membership.company_id if membership else None

    async def connect(self):
        self.company_id = await self.resolve_company_id()
        if not self.company_id:
            await self.close(code=4403)
            return
        self.group_name = f"kitchen_{self.company_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def kitchen_update(self, event):
        await self.send_json({"event": event.get("event", "refresh")})
