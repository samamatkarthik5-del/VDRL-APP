from decimal import Decimal

from django.test import SimpleTestCase

from itp.services.parsing import normalise_header, parse_temperature_range, to_decimal


class ParsingTests(SimpleTestCase):
    def test_header_normalisation(self):
        self.assertEqual(
            normalise_header("NDE APPLICABLE\nFOR BODY/EP"),
            "NDE APPLICABLE FOR BODY EP",
        )

    def test_temperature_range(self):
        minimum, maximum = parse_temperature_range("-46 ~ +32.2")
        self.assertEqual(minimum, Decimal("-46"))
        self.assertEqual(maximum, Decimal("32.2"))

    def test_quantity_conversion(self):
        self.assertEqual(to_decimal("1,299"), Decimal("1299"))
