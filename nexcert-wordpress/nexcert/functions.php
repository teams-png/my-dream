<?php
/**
 * NexCert Global theme setup.
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NEXCERT_VERSION', '1.0.0' );

function nexcert_setup() {
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'html5', array( 'search-form', 'gallery', 'caption', 'script', 'style' ) );

	register_nav_menus(
		array(
			'primary'         => __( 'Primary menu (header)', 'nexcert' ),
			'footer-explore'  => __( 'Footer: Explore', 'nexcert' ),
			'footer-services' => __( 'Footer: Services', 'nexcert' ),
		)
	);
}
add_action( 'after_setup_theme', 'nexcert_setup' );

/**
 * Front-end assets. Elementor's own CSS is enqueued by Elementor itself.
 */
function nexcert_assets() {
	$theme = get_template_directory_uri();
	$ver   = NEXCERT_VERSION;

	wp_enqueue_style( 'nexcert-fonts', 'https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;0,9..144,800;1,9..144,500;1,9..144,600&family=Manrope:wght@400;500;600;700;800&display=swap', array(), null );
	wp_enqueue_style( 'nexcert-style', $theme . '/style.css', array( 'nexcert-fonts' ), $ver );
	wp_enqueue_style( 'nexcert-elementor', $theme . '/assets/css/elementor.css', array( 'nexcert-style' ), $ver );
	wp_enqueue_script( 'nexcert-main', $theme . '/assets/js/main.js', array(), $ver, true );
}
add_action( 'wp_enqueue_scripts', 'nexcert_assets' );

/**
 * Adds a body class the theme CSS can target.
 */
function nexcert_body_class( $classes ) {
	$classes[] = 'nexcert-site';
	return $classes;
}
add_filter( 'body_class', 'nexcert_body_class' );

/**
 * URL of a bundled image in assets/img/.
 */
function nx_asset( $file ) {
	return get_template_directory_uri() . '/assets/img/' . $file;
}

/**
 * Contact details, editable in Appearance > Customize > Contact Details.
 */
function nx_contact( $key ) {
	$defaults = array(
		'nexcert_phone'         => '+974 31393978',
		'nexcert_phone_link'    => '+97431393978',
		'nexcert_phone2'        => '+974 31397878',
		'nexcert_phone2_link'   => '+97431397878',
		'nexcert_email'         => 'info@nexcertglobal.com',
		'nexcert_address'       => 'Doha, State of Qatar',
		'nexcert_hours'         => 'Sunday - Thursday, 8:00 AM - 6:00 PM (AST)',
		'nexcert_enquiry_email' => 'info@nexcertglobal.com',
	);
	return get_theme_mod( $key, $defaults[ $key ] );
}

function nexcert_customize_register( $wp_customize ) {
	$wp_customize->add_section(
		'nexcert_contact',
		array(
			'title'    => __( 'Contact Details', 'nexcert' ),
			'priority' => 30,
		)
	);

	$fields = array(
		'nexcert_phone'         => array( 'Phone (display)', 'text' ),
		'nexcert_phone_link'    => array( 'Phone (dialling format, e.g. +97431393978)', 'text' ),
		'nexcert_phone2'        => array( 'Second phone / WhatsApp (display)', 'text' ),
		'nexcert_phone2_link'   => array( 'Second phone (dialling format)', 'text' ),
		'nexcert_email'         => array( 'Email', 'email' ),
		'nexcert_address'       => array( 'Office address', 'text' ),
		'nexcert_hours'         => array( 'Working hours', 'text' ),
		'nexcert_enquiry_email' => array( 'Where enquiry form messages are sent', 'email' ),
	);

	foreach ( $fields as $key => $field ) {
		$wp_customize->add_setting( $key, array( 'default' => nx_contact( $key ), 'sanitize_callback' => 'sanitize_text_field' ) );
		$wp_customize->add_control( $key, array(
			'label'   => $field[0],
			'section' => 'nexcert_contact',
			'type'    => $field[1],
		) );
	}
}
add_action( 'customize_register', 'nexcert_customize_register' );

require_once get_template_directory() . '/inc/elementor.php';
require_once get_template_directory() . '/inc/pages.php';
require_once get_template_directory() . '/inc/setup.php';
require_once get_template_directory() . '/inc/enquiry-form.php';
