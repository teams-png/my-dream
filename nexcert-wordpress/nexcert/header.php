<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
<meta charset="<?php bloginfo( 'charset' ); ?>">
<meta name="viewport" content="width=device-width, initial-scale=1">
<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<a class="skip-link screen-reader-text" href="#main" style="position:absolute;left:-9999px">Skip to content</a>
<header class="site-header" id="site-header">
	<div class="wrap header-inner">
		<a class="brand" href="<?php echo esc_url( home_url( '/' ) ); ?>"><img src="<?php echo esc_url( nx_asset( 'logo.png' ) ); ?>" alt="NexCert Global"></a>

		<nav class="header-nav" aria-label="Primary">
			<?php
			wp_nav_menu(
				array(
					'theme_location' => 'primary',
					'container'      => false,
					'menu_id'        => 'primary-menu',
					'menu_class'     => 'primary-nav',
					'fallback_cb'    => false,
				)
			);
			?>
		</nav>

		<div class="header-cta">
			<a class="header-phone" href="tel:<?php echo esc_attr( nx_contact( 'nexcert_phone_link' ) ); ?>"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h3l2 5-2 1a12 12 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z"/></svg><span><?php echo esc_html( nx_contact( 'nexcert_phone' ) ); ?></span></a>
			<a class="btn btn--gold" href="<?php echo esc_url( home_url( '/contact/' ) ); ?>">Get a Free GAP AUDIT</a>
			<button class="nav-toggle" aria-expanded="false" aria-controls="primary-menu" aria-label="Toggle menu">
				<span></span><span></span><span></span>
			</button>
		</div>
	</div>
</header>
