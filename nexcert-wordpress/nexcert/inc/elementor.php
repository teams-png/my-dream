<?php
/**
 * Helpers that describe a page in Elementor's own data format.
 *
 * Elementor stores each page as a JSON tree in the `_elementor_data` meta key:
 * section > column > widget. These helpers build that tree so the demo pages
 * are made of ordinary Elementor widgets the client can edit in the editor.
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Random 7-character element id, as Elementor uses.
 */
function nx_el_id() {
	return substr( md5( uniqid( '', true ) . wp_rand() ), 0, 7 );
}

/**
 * A widget. $css is added as the widget's Advanced > CSS Classes.
 */
function nx_el_widget( $type, array $settings = array(), $css = '' ) {
	if ( '' !== $css ) {
		$settings['_css_classes'] = $css;
	}
	return array(
		'id'         => nx_el_id(),
		'elType'     => 'widget',
		'widgetType' => $type,
		'settings'   => (object) $settings,
		'elements'   => array(),
	);
}

/**
 * A column. $size is its width in percent (e.g. 50, 33.33, 25).
 */
function nx_el_col( $size, array $elements, $css = '' ) {
	$settings = array( '_column_size' => $size );
	if ( '' !== $css ) {
		$settings['_css_classes'] = $css;
	}
	return array(
		'id'       => nx_el_id(),
		'elType'   => 'column',
		'settings' => (object) $settings,
		'elements' => $elements,
	);
}

/**
 * A top-level section (a full-width band with a boxed container inside).
 */
function nx_el_section( array $columns, $css = '', $element_id = '' ) {
	$settings = array( 'content_width' => 'boxed' );
	if ( '' !== $css ) {
		$settings['_css_classes'] = $css;
	}
	if ( '' !== $element_id ) {
		$settings['_element_id'] = $element_id;
	}
	return array(
		'id'       => nx_el_id(),
		'elType'   => 'section',
		'settings' => (object) $settings,
		'elements' => $columns,
	);
}

/**
 * A section nested inside a column (used for the trust-bar icon + text).
 */
function nx_el_inner( array $columns, $css = '' ) {
	return array(
		'id'       => nx_el_id(),
		'elType'   => 'section',
		'isInner'  => true,
		'settings' => (object) array( '_css_classes' => trim( 'nx-inner ' . $css ) ),
		'elements' => $columns,
	);
}

/**
 * Heading widget. $tag is h1, h2, h3, ...; $css adds the size class (h-lg, h-md, h-xl).
 */
function nx_el_heading( $text, $tag = 'h2', $css = '', $align = 'left' ) {
	return nx_el_widget(
		'heading',
		array(
			'title'       => $text,
			'header_size' => $tag,
			'align'       => $align,
		),
		$css
	);
}

/**
 * Rich text widget. $html may contain <p>, <strong>, <a>.
 */
function nx_el_text( $html, $css = '' ) {
	return nx_el_widget( 'text-editor', array( 'editor' => $html ), $css );
}

/**
 * Button. $style is gold, ghost or dark.
 */
function nx_el_button( $text, $url, $style = 'gold', $align = 'left', $css = '' ) {
	$classes = trim( 'nx-btn nx-btn--' . $style . ' nx-btn--lg ' . $css );
	return nx_el_widget(
		'button',
		array(
			'text'  => $text,
			'link'  => array(
				'url'         => $url,
				'is_external' => '',
				'nofollow'    => '',
			),
			'align' => $align,
		),
		$classes
	);
}

/**
 * Single photo.
 */
function nx_el_image( $url, $alt, $css = 'nx-media' ) {
	return nx_el_widget(
		'image',
		array(
			'image'      => array(
				'url' => $url,
				'id'  => '',
				'alt' => $alt,
			),
			'image_size' => 'full',
			'align'      => 'center',
		),
		$css
	);
}

/**
 * Auto-playing image carousel (used for the hero slideshow).
 */
function nx_el_carousel( array $urls, $css = 'nx-media nx-hero-carousel' ) {
	$items = array();
	foreach ( $urls as $url ) {
		$items[] = array(
			'id'  => '',
			'url' => $url,
		);
	}
	return nx_el_widget(
		'image-carousel',
		array(
			'carousel'         => $items,
			'image_size'       => 'full',
			'slides_to_show'   => '1',
			'slides_to_scroll' => '1',
			'navigation'       => 'none',
			'pagination'       => 'bullets',
			'autoplay'         => 'yes',
			'autoplay_speed'   => 4200,
			'speed'            => 1200,
			'infinite'         => 'yes',
			'pause_on_hover'   => 'yes',
			'image_stretch'    => 'yes',
		),
		$css
	);
}

/**
 * Raw HTML widget. Use only for icons, decoration and fixed markup.
 */
function nx_el_html( $html, $css = '' ) {
	return nx_el_widget( 'html', array( 'html' => $html ), $css );
}

/**
 * Shortcode widget (used for the enquiry form).
 */
function nx_el_shortcode( $shortcode ) {
	return nx_el_widget( 'shortcode', array( 'shortcode' => $shortcode ) );
}

/**
 * Inline SVG icon, same stroke style as the original design.
 *
 * $parts is a list of shapes. A string starting with "<" is used as markup;
 * any other string is treated as path data for a <path>.
 */
function nx_icon( $parts, $size = 26 ) {
	$shapes = '';
	foreach ( (array) $parts as $part ) {
		$shapes .= ( 0 === strpos( $part, '<' ) ) ? $part : '<path d="' . $part . '"/>';
	}
	return sprintf(
		'<svg width="%1$d" height="%1$d" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%2$s</svg>',
		(int) $size,
		$shapes
	);
}

/**
 * Gold rule with two ticks, the theme's signature divider.
 */
function nx_seal_rule( $center = false ) {
	return nx_el_html(
		'<div class="nx-seal-rule' . ( $center ? ' center' : '' ) . '"><i></i><span></span><i></i></div>'
	);
}

/**
 * Writes a page's sections into Elementor's meta so the page opens in the editor.
 */
function nx_el_save_page( $post_id, array $sections ) {
	update_post_meta( $post_id, '_elementor_edit_mode', 'builder' );
	update_post_meta( $post_id, '_elementor_template_type', 'wp-page' );
	update_post_meta( $post_id, '_elementor_version', defined( 'ELEMENTOR_VERSION' ) ? ELEMENTOR_VERSION : '3.0.0' );
	update_post_meta( $post_id, '_elementor_data', wp_slash( wp_json_encode( $sections ) ) );
	update_post_meta( $post_id, '_wp_page_template', 'default' );

	if ( class_exists( '\Elementor\Plugin' ) && isset( \Elementor\Plugin::$instance->files_manager ) ) {
		\Elementor\Plugin::$instance->files_manager->clear_cache();
	}
}

/**
 * Shared closing band: "Ready to Elevate..." with buttons and contact links.
 */
function nx_cta_band() {
	return nx_el_section(
		array(
			nx_el_col(
				100,
				array(
					nx_el_text( '<p>Start Today</p>', 'eyebrow nx-center' ),
					nx_el_heading( 'Ready to Elevate Your Business Standards?', 'h2', 'h-cta', 'center' ),
					nx_el_text( '<p>Start your certification journey today with Qatar\'s trusted certification partner. Our experts guide you every step of the way — from your first inquiry to your recognized certificate.</p>', 'nx-center' ),
					nx_el_button( 'Get a Free GAP AUDIT', home_url( '/contact/' ), 'gold', 'center' ),
					nx_el_html(
						'<div class="cta-meta"><a href="mailto:' . esc_attr( nx_contact( 'nexcert_email' ) ) . '">' . nx_icon( '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>', 18 ) . ' ' . esc_html( nx_contact( 'nexcert_email' ) ) . '</a>'
						. '<a href="tel:' . esc_attr( nx_contact( 'nexcert_phone_link' ) ) . '">' . nx_icon( '<path d="M6 3h3l2 5-2 1a12 12 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z"/>', 18 ) . ' ' . esc_html( nx_contact( 'nexcert_phone' ) ) . '</a></div>'
					),
				),
				'nx-center'
			),
		),
		'cta-banner skyline-section section'
	);
}
