# NexCert Global — WordPress theme (Elementor-editable)

This folder turns the static site in `public_html.zip` into a WordPress theme with the same design and the same content. Each page is built from ordinary Elementor widgets, so the client can edit text, photos, buttons and the menu without touching code.

## What's here

```
nexcert/                 the theme (install this folder, or the zip made from it)
  style.css              original design system, unchanged from the static site
  assets/css/elementor.css   bridge that makes Elementor widgets look like the original
  assets/js/main.js      header shadow, mobile menu, scroll reveal, hero slideshow
  assets/img/            logo, skyline, icons and banner images from the original
  header.php / footer.php / page.php / index.php
  functions.php          theme setup, menus, Customizer "Contact Details"
  inc/elementor.php      helpers that write pages in Elementor's own format
  inc/pages.php          content of Home, About Us, Services, Contact
  inc/setup.php          one-time setup on activation (pages, menus, front page)
  inc/enquiry-form.php   contact form, sent by email (replaces Formspree)
```

## Install

1. Install and activate **Elementor** (free) from *Plugins > Add New*.
2. Zip the `nexcert` folder (or use `nexcert-theme.zip`) and upload it at *Appearance > Themes > Add New > Upload Theme*, then **Activate** it.
3. Activation creates the four pages (Home, About Us, Services, Contact), the header menu, the footer menus, and sets Home as the front page. It runs once; re-activating later does not overwrite edits.
4. Go to *Appearance > Customize > Contact Details* and check the phone numbers, email, address and working hours. These appear in the header, footer and contact page. Set the email for enquiries there too.
5. Check that the enquiry form sends mail. WordPress `wp_mail()` depends on the host; an SMTP plugin is the reliable option.

Requirements: WordPress 6.0+, PHP 7.4+, Elementor (free).

## Editing with Elementor (for the client)

- Open any page and click **Edit with Elementor**.
- Text is in **Heading** and **Text Editor** widgets. Photos are **Image** widgets. Buttons are **Button** widgets; change the link in the Button's *Link* field.
- Sections (the full-width bands) can have their background changed under *Style*.
- The hero photos are an **Image Carousel**. Add, remove or replace images in its *Content* tab.
- The contact enquiry form is a **Shortcode** widget showing `[nexcert_enquiry]`. Leave it in place; the fields are styled by the theme.
- Header and footer menus are edited under *Appearance > Menus* (locations: *Primary menu*, *Footer: Explore*, *Footer: Services*).

Photos are the same Unsplash images as the original. Upload your own to the Media Library and replace them in Elementor when you have them.

## Things to check on a staging site before going live

This build was checked for correct structure and copy, but it was not run against a live WordPress and Elementor install in this environment. Before the client sees it, open each page in Elementor and on the front end, on desktop and phone width, and check:

- Spacing and alignment of the columns and cards (the Elementor wrappers are styled in `assets/css/elementor.css`).
- The hero carousel's autoplay and dots.
- The enquiry form: submit a test entry and confirm the email arrives.
- The header menu on phone width.

Elementor updates can change internal widget settings. If a widget looks wrong after an update, adjust it in the editor; the content itself is safe because it is stored as normal widget data.
