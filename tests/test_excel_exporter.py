import unittest
import os
import json
import zipfile
import io
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.excel_exporter import export_classes_to_excel, get_class_range_slice, sanitize_sheet_name

class TestExcelExporter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, "timetable.json"), "r", encoding="utf-8") as f:
            cls.tt_data = json.load(f)
        cls.classes = cls.tt_data.get("classes", [])

    def test_sanitize_sheet_name(self):
        self.assertEqual(sanitize_sheet_name("CLASS 6 Rose"), "6 Rose")
        self.assertEqual(sanitize_sheet_name("CLASS 11 (Bio + Math)"), "11 Bio + Math")
        self.assertEqual(sanitize_sheet_name("CLASS 12 (Comm.)"), "12 Comm.")
        # Ensure length <= 31
        long_name = "CLASS Very Long Class Name Exceeding Thirty One Characters"
        self.assertLessEqual(len(sanitize_sheet_name(long_name)), 31)

    def test_get_class_range_slice(self):
        # Middle wing range: Class 6 Rose to Class 8 Lily = 11 classes
        mid = get_class_range_slice(self.classes, "CLASS 6 Rose", "CLASS 8 Lily")
        self.assertEqual(len(mid), 11)
        self.assertEqual(mid[0]["class_name"], "CLASS 6 Rose")
        self.assertEqual(mid[-1]["class_name"], "CLASS 8 Lily")

        # Inverted range test: Class 8 Lily down to Class 6 Rose should yield same 11 classes
        inverted = get_class_range_slice(self.classes, "CLASS 8 Lily", "CLASS 6 Rose")
        self.assertEqual(len(inverted), 11)
        self.assertEqual(inverted[0]["class_name"], "CLASS 6 Rose")

        # Single class
        single = get_class_range_slice(self.classes, "CLASS 7 Marigold", "CLASS 7 Marigold")
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0]["class_name"], "CLASS 7 Marigold")

        # Flexible query test: "6 Rose" to "8 Lily"
        flexible = get_class_range_slice(self.classes, "6 Rose", "8 Lily")
        self.assertEqual(len(flexible), 11)

        # Grade level query test: "6" to "8"
        grade_range = get_class_range_slice(self.classes, "6", "8")
        self.assertEqual(len(grade_range), 11)
        self.assertEqual(grade_range[0]["class_name"], "CLASS 6 Rose")
        self.assertEqual(grade_range[-1]["class_name"], "CLASS 8 Lily")

    def test_export_classes_to_excel_stacked_default(self):
        # Default layout is stacked: Sheet 1 = Master Timetable, Sheet 2 = Range Summary
        xlsx_bytes = export_classes_to_excel(self.classes, "CLASS 6 Rose", "CLASS 8 Lily")
        self.assertIsInstance(xlsx_bytes, bytes)
        self.assertGreater(len(xlsx_bytes), 5000)

        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
            names = z.namelist()
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/styles.xml", names)
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertIn("xl/worksheets/sheet2.xml", names)
            self.assertNotIn("xl/worksheets/sheet3.xml", names)

            # Validate Master Timetable sheet content
            sheet1_content = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            # 1. Class and Class Teacher in same cell with newline
            self.assertIn("CLASS 6 ROSE&#10;Class Teacher:", sheet1_content)
            # 2. Period Numbers and Timings header repeated per class
            self.assertIn("MORNING ASSEMBLY", sheet1_content)
            self.assertIn("1ST PERIOD", sheet1_content)
            self.assertIn("LUNCH BREAK", sheet1_content)
            # 3. Lunch Break locked in Column F
            self.assertIn('c r="F', sheet1_content)

    def test_export_classes_to_excel_tabs_mode(self):
        # Tabs layout: Sheet 1 = Range Summary, Sheets 2..N = Individual class sheets
        xlsx_bytes = export_classes_to_excel(self.classes, "CLASS 6 Rose", "CLASS 8 Lily", layout="tabs")
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
            names = z.namelist()
            self.assertIn("xl/worksheets/sheet1.xml", names)
            # 1 summary + 11 classes = 12 sheets
            self.assertIn("xl/worksheets/sheet12.xml", names)

    def test_export_single_class_excel(self):
        # Stacked layout for a single class produces Master Timetable + Range Summary
        xlsx_bytes = export_classes_to_excel(self.classes, "CLASS 6 Rose", "CLASS 6 Rose", layout="stacked")
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
            names = z.namelist()
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertIn("xl/worksheets/sheet2.xml", names)
            self.assertNotIn("xl/worksheets/sheet3.xml", names)

            sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("CLASS 6 ROSE&#10;Class Teacher: Shruti Badkul", sheet1)

if __name__ == "__main__":
    unittest.main()
