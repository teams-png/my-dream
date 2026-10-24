<?php
/**
 * Enquiry form: the [nexcert_enquiry] shortcode, placed in the Contact page
 * with an Elementor Shortcode widget.
 *
 * The original static site posted to Formspree. Here submissions are checked
 * with a nonce and a honeypot field, then sent by email with wp_mail() to the
 * address set in Appearance > Customize > Contact Details.
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NX_ENQUIRY_SERVICES', array(
	'ISO Certification',
	'ISO & Management System Training',
	'Health & Safety Training',
	'Food Safety Training',
	'Food Safety Audit',
	'Third Party Inspection & Vendor Audit',
	'Multiple Services',
	'Not Sure — I Need Advice',
) );

/**
 * Handles the POST before any output, then redirects (Post/Redirect/Get).
 */
function nx_enquiry_handle() {
	if ( 'POST' !== strtoupper( isset( $_SERVER['REQUEST_METHOD'] ) ? $_SERVER['REQUEST_METHOD'] : '' ) ) {
		return;
	}
	if ( ! isset( $_POST['nx_enquiry_nonce'] ) ) {
		return;
	}

	$back = wp_get_referer() ? wp_get_referer() : home_url( '/contact/' );
	$back = remove_query_arg( 'enquiry', $back );

	if ( ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['nx_enquiry_nonce'] ) ), 'nx_enquiry' ) ) {
		wp_safe_redirect( add_query_arg( 'enquiry', 'invalid', $back ) );
		exit;
	}

	// Honeypot: real visitors never fill this in.
	if ( ! empty( $_POST['nx_website'] ) ) {
		wp_safe_redirect( add_query_arg( 'enquiry', 'sent', $back ) );
		exit;
	}

	$name    = isset( $_POST['full_name'] ) ? sanitize_text_field( wp_unslash( $_POST['full_name'] ) ) : '';
	$company = isset( $_POST['company'] ) ? sanitize_text_field( wp_unslash( $_POST['company'] ) ) : '';
	$email   = isset( $_POST['email'] ) ? sanitize_email( wp_unslash( $_POST['email'] ) ) : '';
	$phone   = isset( $_POST['phone'] ) ? sanitize_text_field( wp_unslash( $_POST['phone'] ) ) : '';
	$service = isset( $_POST['service'] ) ? sanitize_text_field( wp_unslash( $_POST['service'] ) ) : '';
	$message = isset( $_POST['message'] ) ? sanitize_textarea_field( wp_unslash( $_POST['message'] ) ) : '';

	if ( '' === $name || '' === $company || ! is_email( $email ) ) {
		wp_safe_redirect( add_query_arg( 'enquiry', 'invalid', $back ) );
		exit;
	}

	$body = implode(
		"\n",
		array(
			'New enquiry from the NexCert Global website',
			'',
			'Full name: ' . $name,
			'Company: ' . $company,
			'Email: ' . $email,
			'Phone: ' . $phone,
			'Service: ' . $service,
			'',
			'Requirements:',
			$message,
		)
	);

	$sent = wp_mail(
		nx_contact( 'nexcert_enquiry_email' ),
		'New enquiry: ' . $company,
		$body,
		array( 'Reply-To: ' . $name . ' <' . $email . '>' )
	);

	wp_safe_redirect( add_query_arg( 'enquiry', $sent ? 'sent' : 'invalid', $back ) );
	exit;
}
add_action( 'init', 'nx_enquiry_handle' );

/**
 * Renders the form. Same fields and wording as the original page.
 */
function nx_enquiry_shortcode() {
	$status = isset( $_GET['enquiry'] ) ? sanitize_key( wp_unslash( $_GET['enquiry'] ) ) : '';

	ob_start();
	?>
	<div class="form-card" id="enquiry-form">
		<h2>Tell us about your requirements</h2>
		<p class="form-lead">Share a few details and our team will reply with a free, no-obligation quote.</p>

		<?php if ( 'sent' === $status ) : ?>
			<div class="alert alert--ok" role="status">Thank you. Your enquiry has been sent and our team will be in touch shortly.</div>
		<?php elseif ( 'invalid' === $status ) : ?>
			<div class="alert alert--err" role="alert">Please complete the required fields with a valid email address, and try again.</div>
		<?php endif; ?>

		<form action="" method="post">
			<?php wp_nonce_field( 'nx_enquiry', 'nx_enquiry_nonce' ); ?>
			<p class="nx-hp" aria-hidden="true"><label>Leave this field empty <input type="text" name="nx_website" tabindex="-1" autocomplete="off"></label></p>

			<div class="form-grid">
				<div class="field">
					<label for="full_name">Full Name <span class="req">*</span></label>
					<input type="text" id="full_name" name="full_name" required>
				</div>
				<div class="field">
					<label for="company">Company Name <span class="req">*</span></label>
					<input type="text" id="company" name="company" required>
				</div>
				<div class="field">
					<label for="email">Email Address <span class="req">*</span></label>
					<input type="email" id="email" name="email" required>
				</div>
				<div class="field">
					<label for="phone">Phone Number</label>
					<input type="tel" id="phone" name="phone">
				</div>
			</div>

			<div class="field">
				<label for="service">Service Interested In</label>
				<select id="service" name="service">
					<?php foreach ( NX_ENQUIRY_SERVICES as $option ) : ?>
						<option><?php echo esc_html( $option ); ?></option>
					<?php endforeach; ?>
				</select>
			</div>

			<div class="field">
				<label for="message">Message / Tell Us About Your Requirements</label>
				<textarea id="message" name="message"></textarea>
			</div>

			<button type="submit" class="btn btn--gold btn-lg">Submit — Get in Touch</button>
			<p class="form-note">We respect your privacy. Your details are used only to respond to your enquiry.</p>
		</form>
	</div>
	<?php
	return ob_get_clean();
}
add_shortcode( 'nexcert_enquiry', 'nx_enquiry_shortcode' );
