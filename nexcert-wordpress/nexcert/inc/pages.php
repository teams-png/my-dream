<?php
/**
 * Content of the four NexCert pages, written as Elementor sections.
 *
 * Each function returns the section list for one page. The setup routine
 * (inc/setup.php) stores them with nx_el_save_page(), so every heading, text
 * block, button and photo appears in the Elementor editor as a normal widget.
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Unsplash photo URL, as used in the original design.
 */
function nx_photo( $id, $width = 900, $quality = 75 ) {
	return 'https://images.unsplash.com/photo-' . $id . '?auto=format&fit=crop&w=' . (int) $width . '&q=' . (int) $quality;
}

/**
 * Photo card: image, overlapping gold icon, code label, title, text.
 */
function nx_card_media( $photo, $alt, $icon, $title, $text, $code = '' ) {
	$widgets = array(
		nx_el_image( $photo, $alt, 'nx-media' ),
		nx_el_html( nx_icon( $icon, 26 ), 'nx-card-ico' ),
	);
	if ( '' !== $code ) {
		$widgets[] = nx_el_html( '<span class="code" style="display:inline-block;font-weight:800;font-size:.72rem;letter-spacing:.08em;color:var(--gold-deep);margin-bottom:6px">' . esc_html( $code ) . '</span>' );
	}
	$widgets[] = nx_el_heading( $title, 'h3' );
	$widgets[] = nx_el_text( '<p>' . esc_html( $text ) . '</p>' );

	return nx_el_col( 33.33, $widgets, 'nx-card' );
}

/**
 * Plain card with a light icon badge, no photo.
 */
function nx_card_plain( $icon, $title, $text, $width = 33.33 ) {
	return nx_el_col(
		$width,
		array(
			nx_el_html( nx_icon( $icon, 26 ), 'nx-card-ico' ),
			nx_el_heading( $title, 'h3' ),
			nx_el_text( '<p>' . esc_html( $text ) . '</p>' ),
		),
		'nx-card nx-card--plain'
	);
}

/**
 * Trust bar item: icon on the left, bold label and small description on the right.
 */
function nx_trust_item( $icon, $label, $desc, $last = false ) {
	return nx_el_col(
		25,
		array(
			nx_el_inner(
				array(
					nx_el_col( 30, array( nx_el_html( nx_icon( $icon, 22 ), 'nx-trust-ico' ) ) ),
					nx_el_col(
						70,
						array(
							nx_el_text( '<p class="lab">' . esc_html( $label ) . '</p><p class="desc">' . esc_html( $desc ) . '</p>', 'nx-trust-text' ),
						)
					),
				)
			),
		),
		'nx-trust' . ( $last ? ' nx-last' : '' )
	);
}

/**
 * Process step: big number, title, text.
 */
function nx_step( $number, $title, $text ) {
	return nx_el_col(
		25,
		array(
			nx_el_html( '<div class="n">' . (int) $number . '</div>' ),
			nx_el_heading( $title, 'h3' ),
			nx_el_text( '<p>' . esc_html( $text ) . '</p>' ),
		),
		'nx-step'
	);
}

/**
 * Centred section heading block: eyebrow, title, gold rule, optional lead.
 */
function nx_head( $eyebrow, $title, $lead = '', $width = 100 ) {
	$widgets = array(
		nx_el_text( '<p>' . esc_html( $eyebrow ) . '</p>', 'eyebrow' ),
		nx_el_heading( $title, 'h2', 'h-lg', 'center' ),
		nx_seal_rule( true ),
	);
	if ( '' !== $lead ) {
		$widgets[] = nx_el_text( '<p>' . esc_html( $lead ) . '</p>', 'lead' );
	}
	return nx_el_col( $width, $widgets, 'nx-center nx-head' );
}

/* =====================================================================
   HOME
   ===================================================================== */
function nx_page_home() {
	$hero_photos = array(
		nx_photo( '1573167507387-6b4b98cb7c13', 1000, 75 ),
		nx_photo( '1672954766589-49f0dd0e106f', 1000, 75 ),
		nx_photo( '1551884170-09fb70a3a2ed', 1000, 75 ),
		nx_photo( '1556761175-5973dc0f32e7', 1000, 75 ),
	);

	$trust = nx_el_section(
		array(
			nx_trust_item( array( 'M5 21V4M5 4h11l-2 4 2 4H5' ), 'Qatar-Based Team', 'Local presence, responsive support, in English and Arabic.' ),
			nx_trust_item( array( 'm12 3 2.6 5.5 6 .8-4.4 4.2 1.1 6L12 16.8 6.7 19.5l1.1-6L3.4 9.3l6-.8z' ), 'Full-Service Partner', 'Certification, training, and audits under one roof.' ),
			nx_trust_item( array( 'M20 12 12 20l-8-8V4h8z', '<circle cx="8.5" cy="8.5" r="1.3" fill="currentColor"/>' ), 'Transparent Pricing', 'Clear, fair quotes with no hidden fees.' ),
			nx_trust_item( array( 'm12 11 3-3 5 5-2 2-3-3', 'm12 11-3-3-5 5 2 2 3-3', 'm9 14 3 3 3-3' ), 'Multi-Industry Experience', 'Working with businesses of every size, across every sector.', true ),
		),
		'trustbar'
	);

	$services = array(
		nx_card_media( nx_photo( '1542744173-8e7e53415bb0' ), 'ISO Certification', array( 'M12 2 4 5v6c0 5 3.4 8.4 8 11 4.6-2.6 8-6 8-11V5z', 'm9 12 2 2 4-4' ), 'ISO Certification', 'Certification for ISO 9001, 14001, 45001, 22000, 27001, 37001, and 50001.' ),
		nx_card_media( nx_photo( '1556761175-5973dc0f32e7' ), 'ISO & Management System Training', array( 'M4 4h11a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2.5H4z', 'M4 4v13.5' ), 'ISO & Management System Training', 'Lead Auditor, Internal Auditor training delivered by experienced practitioners.' ),
		nx_card_media( nx_photo( '1672954766589-49f0dd0e106f' ), 'Health & Safety Training', array( 'M3 13a9 9 0 0 1 18 0', 'M2 13h20v3a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z', 'M12 4v5' ), 'Health & Safety Training', 'Practical H&S programs that build a genuine safety culture and support Qatar regulatory compliance.' ),
		nx_card_media( nx_photo( '1551884170-09fb70a3a2ed' ), 'Food Safety Training', array( '<circle cx="12" cy="12" r="8"/>', '<circle cx="12" cy="12" r="3"/>' ), 'Food Safety Training', 'HACCP, ISO 22000 awareness, and food handler training aligned with Qatar MOPH requirements.' ),
		nx_card_media( nx_photo( '1551884171-004163219904' ), 'Food Safety Audit', array( '<circle cx="11" cy="11" r="7"/>', '<path d="m21 21-4.3-4.3"/>' ), 'Food Safety Audit', 'Independent Assessment of International Food Safety Practices.' ),
		nx_card_media( nx_photo( '1573164574572-cb89e39749b4' ), 'Third Party Inspections & Vendor Audits', array( '<rect x="6" y="4" width="12" height="17" rx="2"/>', '<path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1"/>', '<path d="M9 11h6M9 15h4"/>' ), 'Third Party Inspections & Vendor Audits', 'Independent audits that give you full visibility into your supply chain.' ),
	);

	$advantage = array(
		nx_el_col( 50, array( nx_el_html( '<span class="adv-ico">' . nx_icon( '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>', 22 ) . '</span>' ), nx_el_heading( 'Fair, Transparent Pricing', 'h3' ), nx_el_text( '<p>Accessible packages for SMEs, traders, and enterprises, with no hidden fees.</p>' ) ), 'nx-adv' ),
		nx_el_col( 50, array( nx_el_html( '<span class="adv-ico">' . nx_icon( '<path d="M20 7 12 3 4 7l8 4 8-4Z"/><path d="M4 7v10l8 4 8-4V7"/><path d="M12 11v10"/>', 22 ) . '</span>' ), nx_el_heading( 'Full-Service Partner', 'h3' ), nx_el_text( '<p>Certification, training, and audits handled by one dedicated team, start to finish.</p>' ) ), 'nx-adv' ),
		nx_el_col( 50, array( nx_el_html( '<span class="adv-ico">' . nx_icon( '<path d="M12 21s-7-4.6-9.3-9.3C1.4 8.2 3.4 5 6.8 5c1.8 0 3.3 1 4.1 2.3C11.7 6 13.2 5 15 5c3.4 0 5.4 3.2 4.1 6.7C16.9 16.4 12 21 12 21Z"/>', 22 ) . '</span>' ), nx_el_heading( 'Local Presence', 'h3' ), nx_el_text( '<p>A Qatar-based team serving you in English and Arabic, with a genuine understanding of the local market.</p>' ) ), 'nx-adv' ),
		nx_el_col( 50, array( nx_el_html( '<span class="adv-ico">' . nx_icon( '<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 3v9l6 3"/>', 22 ) . '</span>' ), nx_el_heading( 'Practical, Client-Centered Approach', 'h3' ), nx_el_text( '<p>Every engagement is shaped around your business, not a generic checklist.</p>' ) ), 'nx-adv' ),
	);

	return array(
		// Hero: headline and buttons on the left, slideshow on the right.
		nx_el_section(
			array(
				nx_el_col(
					57.5,
					array(
						nx_el_heading( 'Qatar\'s Trusted Partner for ISO Certification, Training & Audits', 'h1', 'h-xl' ),
						nx_el_text( '<p>Practical, transparent, and fairly priced. NexCert Global helps businesses across Qatar achieve ISO certification, build stronger management systems, and stay compliant — with a Qatar-based team that understands your market.</p>', 'nx-hero-body' ),
						nx_el_button( 'Get a Free GAP AUDIT Today', home_url( '/contact/' ), 'gold', 'left', 'nx-btn-inline' ),
						nx_el_button( 'Explore Our Services', home_url( '/services/' ), 'ghost', 'left', 'nx-btn-inline' ),
					)
				),
				nx_el_col( 42.5, array( nx_el_carousel( $hero_photos ) ) ),
			),
			'hero skyline-section'
		),

		$trust,

		// Purpose.
		nx_el_section(
			array(
				nx_el_col( 50, array( nx_el_image( nx_photo( '1541888946425-d81bb19240f5', 900, 70 ), 'NexCert Global auditors at work', 'nx-media nx-media-portrait' ) ) ),
				nx_el_col(
					50,
					array(
						nx_el_text( '<p>Our Purpose</p>', 'eyebrow' ),
						nx_el_heading( 'Why NexCert Global Exists', 'h2', 'h-lg' ),
						nx_seal_rule(),
						nx_el_text( '<p>In a rapidly evolving business landscape, compliance and quality are no longer optional — they are the foundation of lasting success. NexCert Global was established to bridge a gap in Qatar\'s certification market: the need for a trusted, fairly priced certification partner that understands the challenges businesses in the region actually face. We give our clients — and their customers — confidence in every certificate we issue.</p>' ),
						nx_el_text( '<p>Our Qatar-based team of auditors and trainers works alongside your organization to make the certification journey straightforward, transparent, and genuinely useful — combining sound technical expertise with a practical, local understanding of how business gets done in Qatar.</p>', 'nx-muted' ),
					)
				),
			),
			'bg-paper section'
		),

		// Core services.
		nx_el_section(
			array_merge(
				array( nx_head( 'What We Do', 'Our Core Services', 'From ISO certification to specialized training and audits — NexCert Global is your end-to-end partner in quality, safety, and compliance.' ) ),
				$services,
				array(
					nx_el_col(
						100,
						array( nx_el_button( 'View All Services', home_url( '/services/' ), 'dark', 'center' ) ),
						'nx-center nx-more'
					),
				)
			),
			'bg-cream section'
		),

		// Advantages.
		nx_el_section(
			array_merge(
				array( nx_head( 'Our Advantage', 'Why Businesses in Qatar Choose NexCert Global' ) ),
				$advantage
			),
			'bg-cream section'
		),

		nx_cta_band(),
	);
}

/* =====================================================================
   ABOUT
   ===================================================================== */
function nx_page_about() {
	return array(
		nx_el_section(
			array(
				nx_el_col(
					100,
					array(
						nx_el_text( '<p>About NexCert Global</p>', 'eyebrow' ),
						nx_el_heading( 'About NexCert Global', 'h1' ),
						nx_el_text( '<p>Connecting Qatar\'s Businesses to Practical, Recognized Quality Standards</p>' ),
					),
					'nx-center'
				),
			),
			'page-hero'
		),

		nx_el_section(
			array(
				nx_el_col(
					50,
					array(
						nx_el_text( '<p>Our Story</p>', 'eyebrow' ),
						nx_el_heading( 'Connecting Qatar\'s Businesses to Practical, Recognized Quality Standards', 'h2', 'h-lg' ),
						nx_seal_rule(),
						nx_el_text( '<p>NexCert Global for Quality and Accreditation was founded with a clear purpose: to make certification and training genuinely accessible to businesses of every size operating in Qatar and the wider Gulf region.</p>' ),
						nx_el_text( '<p>We saw that while demand for ISO certification in Qatar was growing rapidly — driven by global trade requirements, Qatar National Vision 2030, and increasingly demanding supply chains — many businesses found the process too complex, too costly, or disconnected from the realities of the local market.</p>', 'nx-muted' ),
						nx_el_text( '<p>That is why NexCert Global was built around a simple idea: bring together sound technical expertise and a dedicated local team, fully focused on making the certification journey clear, practical, and fairly priced.</p>', 'nx-muted' ),
						nx_el_text( '<p>From our base in Doha, we work with businesses across every sector — from SMEs taking their first steps toward ISO certification to established enterprises strengthening their quality, safety, and environmental systems. Our aim is simple: certification that is credible, transparent, fairly priced, and genuinely valuable.</p>', 'nx-muted' ),
					)
				),
				nx_el_col( 50, array( nx_el_image( nx_photo( '1573164574572-cb89e39749b4' ), 'NexCert Global team at work', 'nx-media' ) ) ),
			),
			'bg-paper section'
		),

		nx_el_section(
			array(
				nx_el_col(
					50,
					array(
						nx_el_text( '<p>Our Vision</p>', 'eyebrow' ),
						nx_el_heading( 'The Most Trusted Certification Partner in the Gulf', 'h3', 'h-md' ),
						nx_el_text( '<p>To be the most trusted and accessible certification and training partner for businesses in Qatar and the Gulf region — empowering organizations of every size to reach recognized standards of quality, safety, and operational excellence.</p>' ),
					),
					'nx-callout'
				),
				nx_el_col(
					50,
					array(
						nx_el_text( '<p>Our Mission</p>', 'eyebrow' ),
						nx_el_heading( 'Rigorous, Transparent, Fairly Priced', 'h3', 'h-md' ),
						nx_el_text( '<p>To deliver rigorous, transparent, and fairly priced certification, training, and audit services that help businesses in Qatar build stronger systems, meet local and global requirements, and unlock new opportunities for growth.</p>' ),
					),
					'nx-callout'
				),
			),
			'bg-paper section'
		),

		nx_el_section(
			array_merge(
				array( nx_head( 'What Guides Us', 'Our Core Values' ) ),
				array(
					nx_card_plain( array( '<circle cx="11" cy="11" r="7"/>', '<path d="m21 21-4.3-4.3"/>' ), 'Integrity', 'Every audit, assessment, and training session is conducted with independence, transparency, and honesty.' ),
					nx_card_plain( array( '<circle cx="12" cy="12" r="9"/>', '<path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/>' ), 'Global Standards, Local Understanding', 'We combine sound technical practice with a genuine understanding of Qatar\'s regulatory environment and business culture.' ),
					nx_card_plain( array( 'm12 3 2.6 5.5 6 .8-4.4 4.2 1.1 6L12 16.8 6.7 19.5l1.1-6L3.4 9.3l6-.8z' ), 'Client-Centricity', 'Every business is different. We take time to understand your industry, your challenges, and your goals before shaping a certification path that works for you.' ),
					nx_card_plain( array( '<path d="M4 18a8 8 0 1 1 16 0"/>', '<path d="m12 14 4-4"/>' ), 'Continuous Improvement', 'We hold ourselves to the same standard we certify. NexCert Global continually invests in the development of our auditors, trainers, and processes.' ),
					nx_card_plain( array( 'm12 11 3-3 5 5-2 2-3-3', 'm12 11-3-3-5 5 2 2 3-3', 'm9 14 3 3 3-3' ), 'Partnership', 'We see ourselves as long-term partners in your quality journey — from your first inquiry through annual surveillance audits and recertification.' ),
				)
			),
			'bg-paper section'
		),

		nx_cta_band(),
	);
}

/* =====================================================================
   SERVICES
   ===================================================================== */
function nx_page_services() {
	$standards = array(
		array( 'ISO 9001', 'Quality Management System', 'The world\'s most recognized quality standard — consistent delivery of products and services meeting customer and regulatory requirements, with continuous improvement built in.', array( 'M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z' ) ),
		array( 'ISO 14001', 'Environmental Management System', 'A structured framework to identify, manage, and minimize environmental impact.', array( 'M11 20A7 7 0 0 1 4 13c0-4 3-7 8-11 5 4 8 7 8 11a7 7 0 0 1-7 7', 'M11 20a7 7 0 0 1-7-7c0-1 .2-2 .6-3' ) ),
		array( 'ISO 45001', 'Occupational Health & Safety Management System', 'The international framework to prevent workplace injuries and proactively improve safety.', array( 'M12 2 4 5v6c0 5 3.4 9 8 11 4.6-2 8-6 8-11V5l-8-3Z' ) ),
		array( 'ISO 22000', 'Food Safety Management System', 'Integrates HACCP principles with management system requirements for safe food at every stage.', array( 'M18 8h1a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2h-1', 'M3 8h13v6a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5V8Z', 'M6 2v3M10 2v3M14 2v3' ) ),
		array( 'ISO 27001', 'Information Security Management System', 'Systematic framework for protecting information assets and managing cybersecurity risk.', array( '<rect x="4" y="10" width="16" height="10" rx="2"/>', '<path d="M8 10V7a4 4 0 0 1 8 0v3"/>' ) ),
		array( 'ISO 37001', 'Anti-Bribery Management System', 'Robust controls to prevent, detect, and address bribery within your organization.', array( 'M12 3v18M7 7 3 15a4 4 0 0 0 8 0L7 7ZM17 7l-4 8a4 4 0 0 0 8 0l-4-8ZM5 21h14' ) ),
		array( 'ISO 50001', 'Energy Management System', 'Systematic approach to optimizing energy use and demonstrating environmental responsibility.', array( 'm13 2-9 12h6l-1 8 9-12h-6l1-8Z' ) ),
	);

	$standard_cols = array();
	foreach ( $standards as $std ) {
		$standard_cols[] = nx_el_col(
			50,
			array(
				nx_el_html( '<span class="std-ico">' . nx_icon( $std[3], 20 ) . '</span>' ),
				nx_el_html( '<span class="code">' . esc_html( $std[0] ) . '</span>' ),
				nx_el_heading( $std[1], 'h3' ),
				nx_el_text( '<p>' . esc_html( $std[2] ) . '</p>', 'std-desc' ),
			),
			'nx-std'
		);
	}

	$steps = array(
		array( 'Application & Gap Audit', 'We review your organization\'s scope and current systems, and identify what is needed before the formal audit.' ),
		array( 'Stage 1 Audit — Documentation Review', 'Our auditors review your management system documentation and confirm readiness for the on-site assessment.' ),
		array( 'Stage 2 Audit — On-Site Assessment', 'Qualified auditors assess your management system in practice, evaluating conformance to the standard.' ),
		array( 'Certificate Issued', 'Your certificate is issued, with annual surveillance audits and recertification every three years.' ),
	);
	$step_cols = array();
	foreach ( $steps as $i => $step ) {
		$step_cols[] = nx_step( $i + 1, $step[0], $step[1] );
	}

	$programmes = array(
		array( 'Lead Auditor Training', 'ISO 9001 / 14001 / 45001 / 22000 / 27001', '5 days' ),
		array( 'Internal Auditor Training', 'Equip your internal team to conduct effective, value-adding audits that drive real improvement.', '2 days' ),
	);
	$programme_cols = array();
	foreach ( $programmes as $prog ) {
		$programme_cols[] = nx_el_col(
			50,
			array(
				nx_el_heading( $prog[0], 'h3' ),
				nx_el_text( '<p>' . esc_html( $prog[1] ) . '</p>' ),
				nx_el_html( '<div class="meta"><span>' . esc_html( $prog[2] ) . '</span><span>Classroom / In-house</span><span>English / Arabic</span></div>' ),
			),
			'nx-prog'
		);
	}

	return array(
		nx_el_section(
			array(
				nx_el_col(
					100,
					array(
						nx_el_text( '<p>Area of Expertise</p>', 'eyebrow' ),
						nx_el_heading( 'Our Services', 'h1' ),
						nx_el_text( '<p>End-to-End Certification, Training &amp; Audit Services.</p>' ),
					),
					'nx-center'
				),
			),
			'page-hero'
		),

		// Service 01: ISO certification and the standards list.
		nx_el_section(
			array_merge(
				array(
					nx_el_col(
						50,
						array(
							nx_el_text( '<p>Service 01</p>', 'eyebrow' ),
							nx_el_heading( 'ISO Certification', 'h2', 'h-lg' ),
							nx_seal_rule(),
							nx_el_text( '<p>ISO certification is a recognized benchmark for quality, safety, environmental responsibility, and operational excellence. NexCert Global supports your organization through every stage of the certification journey, across the following standards:</p>', 'lead' ),
						),
						'nx-head'
					),
					nx_el_col( 50, array( nx_el_image( nx_photo( '1542744173-8e7e53415bb0' ), 'ISO certification briefing', 'nx-media' ) ), 'nx-head' ),
					nx_el_col( 100, array( nx_el_heading( 'ISO Standards We Certify', 'h3', 'h-md' ) ), 'nx-subhead' ),
				),
				$standard_cols,
				array( nx_el_col( 100, array( nx_el_image( nx_photo( '1573164574572-cb89e39749b4', 1600, 70 ), 'Auditors reviewing documentation', 'nx-media nx-media-wide' ) ), 'nx-more' ) )
			),
			'bg-paper section',
			'iso-certification'
		),

		// Certification process.
		nx_el_section(
			array_merge(
				array( nx_head( 'How It Works', 'Our Certification Process' ) ),
				$step_cols
			),
			'bg-paper section'
		),

		// Service 02: training.
		nx_el_section(
			array_merge(
				array(
					nx_el_col(
						50,
						array(
							nx_el_text( '<p>Service 02</p>', 'eyebrow' ),
							nx_el_heading( 'ISO & Management System Training', 'h2', 'h-lg' ),
							nx_seal_rule(),
							nx_el_text( '<p>Practical training that builds real capability inside your organization — delivered by experienced auditors who know what a strong management system looks like from the inside.</p>', 'lead' ),
						),
						'nx-head'
					),
					nx_el_col( 50, array( nx_el_image( nx_photo( '1556761175-5973dc0f32e7' ), 'ISO and management system training session', 'nx-media' ) ), 'nx-head' ),
				),
				$programme_cols
			),
			'bg-paper section',
			'training'
		),

		// Services 03–06.
		nx_el_section(
			array(
				nx_card_media( nx_photo( '1672954766589-49f0dd0e106f' ), 'Health & Safety Training', array( 'M3 13a9 9 0 0 1 18 0', 'M2 13h20v3a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z', 'M12 4v5' ), 'Health & Safety Training', 'Programs that create a genuine safety culture at every level of your organization, reduce the risk of incidents, and support compliance with Qatar\'s occupational health and safety requirements, including ASHGHAL and MMUP.', 'SERVICE 03' ),
				nx_card_media( nx_photo( '1551884170-09fb70a3a2ed' ), 'Food Safety Training', array( '<circle cx="12" cy="12" r="8"/>', '<circle cx="12" cy="12" r="3"/>' ), 'Food Safety Training', 'Training aligned with Qatar MOPH requirements, giving your team the knowledge to protect consumers, your brand, and your operating license.', 'SERVICE 04' ),
				nx_card_media( nx_photo( '1551884171-004163219904' ), 'Food Safety Audit', array( '<circle cx="11" cy="11" r="7"/>', '<path d="m21 21-4.3-4.3"/>' ), 'Food Safety Audit', 'Independent Assessment of International Food Safety Practices.', 'SERVICE 05' ),
				nx_card_media( nx_photo( '1573164574572-cb89e39749b4' ), 'Third Party Inspections & Vendor Audits', array( '<rect x="6" y="4" width="12" height="17" rx="2"/>', '<path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1"/>', '<path d="M9 11h6M9 15h4"/>' ), 'Third Party Inspections & Vendor Audits', 'Independent audits and inspections that give you full visibility into your supply chain — protecting your quality, safety, and commercial reputation.', 'SERVICE 06' ),
			),
			'bg-paper section'
		),

		nx_cta_band(),
	);
}

/* =====================================================================
   CONTACT
   ===================================================================== */
function nx_page_contact() {
	$ico_phone = '<path d="M6 3h3l2 5-2 1a12 12 0 0 0 5 5l1-2 5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z"/>';
	$ico_mail  = '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>';
	$ico_pin   = '<path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>';
	$ico_clock = '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>';

	$info_row = function ( $icon, $label, $value_html ) {
		return '<div class="info-row"><span class="ir-ico">' . nx_icon( $icon, 22 ) . '</span><div><div class="ir-lab">' . esc_html( $label ) . '</div><div class="ir-val">' . $value_html . '</div></div></div>';
	};

	$aside = '<div class="contact-aside">'
		. $info_row( $ico_phone, 'Phone / WhatsApp', '<a href="tel:' . esc_attr( nx_contact( 'nexcert_phone2_link' ) ) . '">' . esc_html( nx_contact( 'nexcert_phone2' ) ) . '</a>' )
		. $info_row( $ico_mail, 'Email', '<a href="mailto:' . esc_attr( nx_contact( 'nexcert_email' ) ) . '">' . esc_html( nx_contact( 'nexcert_email' ) ) . '</a>' )
		. $info_row( $ico_pin, 'Office', esc_html( nx_contact( 'nexcert_address' ) ) )
		. $info_row( $ico_clock, 'Working Hours', '<span style="font-size:.95rem;font-weight:500">' . esc_html( nx_contact( 'nexcert_hours' ) ) . '</span>' )
		. '<div class="quickref"><h4>Services Quick Reference</h4><div class="qchips">'
		. '<span>ISO 9001</span><span>ISO 14001</span><span>ISO 45001</span><span>ISO 22000</span><span>ISO 27001</span><span>ISO 37001</span><span>ISO 50001</span>'
		. '<span>Lead Auditor</span><span>Internal Auditor</span><span>H&amp;S Training</span><span>Food Safety</span><span>Vendor Audits</span><span>Third-Party Inspections</span>'
		. '</div></div></div>';

	return array(
		nx_el_section(
			array(
				nx_el_col(
					100,
					array(
						nx_el_text( '<p>Contact</p>', 'eyebrow' ),
						nx_el_heading( 'Contact NexCert Global', 'h1' ),
						nx_el_text( '<p>Qatar\'s Certification, Training &amp; Audit Partner Is Ready to Help.</p>' ),
					),
					'nx-center'
				),
			),
			'page-hero'
		),

		nx_el_section(
			array(
				nx_el_col( 55, array( nx_el_shortcode( '[nexcert_enquiry]' ) ), 'nx-form-col' ),
				nx_el_col( 45, array( nx_el_html( $aside ) ), 'nx-info-col' ),
			),
			'bg-paper section',
			'enquiry'
		),

		nx_cta_band(),
	);
}
