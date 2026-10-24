<?php
/**
 * Fallback template (blog index, search, 404).
 *
 * @package NexCert
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();
?>
<main id="main" class="nx-page">
	<section class="section bg-paper">
		<div class="wrap narrow">
			<?php if ( have_posts() ) : ?>
				<?php while ( have_posts() ) : the_post(); ?>
					<article <?php post_class(); ?>>
						<h2 class="h-md"><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h2>
						<div><?php the_excerpt(); ?></div>
					</article>
				<?php endwhile; ?>
			<?php else : ?>
				<h1 class="h-lg">Page not found</h1>
				<p class="lead"><a href="<?php echo esc_url( home_url( '/' ) ); ?>">Return to the home page</a></p>
			<?php endif; ?>
		</div>
	</section>
</main>
<?php
get_footer();
