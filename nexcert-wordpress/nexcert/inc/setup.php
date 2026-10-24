<?php
/**
 * One-time site setup, run when the theme is activated.
 *
 * Creates the Home, About, Services and Contact pages (as Elementor pages),
 * the header and footer menus, and sets Home as the front page.
 * It runs once: the option "nexcert_setup_version" marks it as done, so a
 * later re-activation never overwrites the client's edits.
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NEXCERT_SETUP_VERSION', '1.0.0' );

add_action( 'after_switch_theme', 'nx_run_setup' );

function nx_run_setup() {
	if ( get_option( 'nexcert_setup_version' ) === NEXCERT_SETUP_VERSION ) {
		return;
	}

	// Pretty permalinks, so /contact/ and friends work.
	update_option( 'permalink_structure', '/%postname%/' );

	$pages = array(
		'home'     => array( 'Home', 'nx_page_home' ),
		'about'    => array( 'About Us', 'nx_page_about' ),
		'services' => array( 'Services', 'nx_page_services' ),
		'contact'  => array( 'Contact', 'nx_page_contact' ),
	);

	$ids = array();
	foreach ( $pages as $slug => $page ) {
		$ids[ $slug ] = nx_setup_page( $slug, $page[0], $page[1] );
	}

	if ( $ids['home'] ) {
		update_option( 'show_on_front', 'page' );
		update_option( 'page_on_front', $ids['home'] );
	}

	nx_setup_menu(
		'NexCert Header',
		'primary',
		array(
			$ids['home'],
			$ids['about'],
			$ids['services'],
			$ids['contact'],
		)
	);

	nx_setup_menu(
		'NexCert Footer: Explore',
		'footer-explore',
		array(
			$ids['home'],
			$ids['about'],
			$ids['services'],
			$ids['contact'],
		)
	);

	nx_setup_menu(
		'NexCert Footer: Services',
		'footer-services',
		array(
			array( 'ISO Certification', $ids['services'], '#iso-certification' ),
			array( 'ISO & MS Training', $ids['services'], '#training' ),
			array( 'Health & Safety Training', $ids['services'] ),
			array( 'Food Safety Training & Audit', $ids['services'] ),
			array( 'Third Party & Vendor Audits', $ids['services'] ),
		)
	);

	flush_rewrite_rules();
	update_option( 'nexcert_setup_version', NEXCERT_SETUP_VERSION );
}

/**
 * Creates (or finds) a page and writes its Elementor layout.
 */
function nx_setup_page( $slug, $title, $builder ) {
	$page = get_page_by_path( $slug );
	if ( $page ) {
		$id = $page->ID;
	} else {
		$id = wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'publish',
				'post_title'   => $title,
				'post_name'    => $slug,
				'post_content' => '',
			),
			true
		);
		if ( is_wp_error( $id ) ) {
			return 0;
		}
	}

	nx_el_save_page( $id, call_user_func( $builder ) );

	return (int) $id;
}

/**
 * Creates a menu and fills it. Each item is a page ID, or an array of
 * [label, page ID, optional #anchor].
 */
function nx_setup_menu( $name, $location, array $items ) {
	$menu    = wp_get_nav_menu_object( $name );
	$menu_id = $menu ? $menu->term_id : wp_create_nav_menu( $name );
	if ( is_wp_error( $menu_id ) ) {
		return;
	}

	foreach ( (array) wp_get_nav_menu_items( $menu_id ) as $existing ) {
		wp_delete_post( $existing->ID, true );
	}

	foreach ( $items as $item ) {
		$args = array(
			'menu-item-status' => 'publish',
			'menu-item-type'   => 'post_type',
			'menu-item-object' => 'page',
		);

		if ( is_array( $item ) ) {
			$page_id          = $item[1];
			$args['menu-item-title'] = $item[0];
			$anchor           = isset( $item[2] ) ? $item[2] : '';
		} else {
			$page_id = $item;
			$anchor  = '';
		}

		if ( ! $page_id ) {
			continue;
		}

		$args['menu-item-object-id'] = $page_id;
		if ( '' !== $anchor ) {
			$args['menu-item-type'] = 'custom';
			$args['menu-item-url']  = get_permalink( $page_id ) . $anchor;
			unset( $args['menu-item-object'], $args['menu-item-object-id'] );
		}

		wp_update_nav_menu_item( $menu_id, 0, $args );
	}

	$locations              = get_theme_mod( 'nav_menu_locations', array() );
	$locations[ $location ] = $menu_id;
	set_theme_mod( 'nav_menu_locations', $locations );
}

/**
 * Reminds the admin to install Elementor, which the pages need to be edited.
 */
function nx_elementor_notice() {
	if ( did_action( 'elementor/loaded' ) || ! current_user_can( 'activate_plugins' ) ) {
		return;
	}
	echo '<div class="notice notice-warning"><p><strong>NexCert Global:</strong> install and activate the free <em>Elementor</em> plugin to edit the site pages.</p></div>';
}
add_action( 'admin_notices', 'nx_elementor_notice' );
