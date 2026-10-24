<footer class="site-footer">
	<div class="footer-skyline" aria-hidden="true"></div>
	<div class="wrap">
		<div class="footer-top">
			<div class="footer-brand footer-col">
				<img src="<?php echo esc_url( nx_asset( 'logo.png' ) ); ?>" alt="NexCert Global">
				<p>Qatar-Based ISO Certification, Training &amp; Audit Services.</p>
			</div>

			<div class="footer-col">
				<h4>Explore</h4>
				<?php
				wp_nav_menu(
					array(
						'theme_location' => 'footer-explore',
						'container'      => false,
						'items_wrap'     => '<ul>%3$s</ul>',
						'fallback_cb'    => false,
					)
				);
				?>
			</div>

			<div class="footer-col">
				<h4>Services</h4>
				<?php
				wp_nav_menu(
					array(
						'theme_location' => 'footer-services',
						'container'      => false,
						'items_wrap'     => '<ul>%3$s</ul>',
						'fallback_cb'    => false,
					)
				);
				?>
			</div>

			<div class="footer-col">
				<h4>Get in Touch</h4>
				<ul>
					<li><a href="tel:<?php echo esc_attr( nx_contact( 'nexcert_phone_link' ) ); ?>"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h3l2 5-2 1a12 12 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z"/></svg> <?php echo esc_html( nx_contact( 'nexcert_phone' ) ); ?></a></li>
					<li><a href="mailto:<?php echo esc_attr( nx_contact( 'nexcert_email' ) ); ?>"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg> <?php echo esc_html( nx_contact( 'nexcert_email' ) ); ?></a></li>
					<li><span style="display:inline-flex;gap:8px;align-items:flex-start"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg> <?php echo esc_html( nx_contact( 'nexcert_address' ) ); ?></span></li>
					<li><span style="display:inline-flex;gap:8px;align-items:flex-start"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg> <?php echo esc_html( nx_contact( 'nexcert_hours' ) ); ?></span></li>
				</ul>
			</div>
		</div>

		<div class="footer-bottom">
			<span>&copy; <?php echo esc_html( gmdate( 'Y' ) ); ?> NexCert Global for Quality and Accreditation. All rights reserved.</span>
		</div>
	</div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
