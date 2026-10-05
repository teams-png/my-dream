# Same number and input formats as English: prices are read by JavaScript and date pickers send ISO dates.
from django.conf.locale.en.formats import DATE_INPUT_FORMATS, DATETIME_INPUT_FORMATS, TIME_INPUT_FORMATS  # noqa: F401

DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3
