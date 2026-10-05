BookPilot customer user guide (English / Malayalam / Arabic)

Source for the guide served by the app at /guide/.

Edit the content here, then rebuild:
    cd docs/user-guide && python3 build.py
The pages are written to apps/webapp/guide_site/ — commit them with your change.
A test fails if the built pages are out of date.

Files:
  engine.py         page layout and CONFIG (contact details are filled in by the app from
                    the SUPPORT_EMAIL, SUPPORT_WHATSAPP and LEGAL_COMPANY_NAME settings)
  i18n.py           interface words, group names and guide names per language
  common*.py        Getting started and Help pages (en / ml / ar)
  verticals_a..d.py business-type guides;  features.py  tools every business uses
  tr_ml*.py tr_ar.py  Malayalam / Arabic text for the business guides
