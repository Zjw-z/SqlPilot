import unittest
from datetime import date

from app.engine import TrustworthyQueryEngine
from app.planner import understand


class PlannerTests(unittest.TestCase):
    def test_extracts_certified_metric_dimensions_and_year(self):
        plan = understand("统计2025年各医院每月基金支付金额及环比", date(2026, 8, 25))
        self.assertEqual(plan.metric.key, "fund_pay_total")
        self.assertEqual({item.key for item in plan.dimensions}, {"month", "institution"})
        self.assertEqual(plan.start_date, "2025-01-01")
        self.assertEqual(plan.comparison, "mom")

    def test_ambiguous_fee_requires_confirmation(self):
        result = TrustworthyQueryEngine().run("看看2025年各医院费用情况")
        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["trust"]["level"], "B")

    def test_understands_current_year_inpatient_yoy_growth_request(self):
        plan = understand(
            "统计下今年各医疗机构的住院医保基金使用情况，和同期进行比较，看哪个月的费用增长较高",
            date(2026, 8, 25),
        )
        self.assertEqual(plan.start_date, "2026-01-01")
        self.assertEqual(plan.end_date, "2026-08-25")
        self.assertEqual(plan.metric.key, "fund_pay_total")
        self.assertEqual({item.key for item in plan.dimensions}, {"month", "institution"})
        self.assertEqual(plan.medical_type, "inpatient")
        self.assertEqual(plan.comparison, "yoy")
        self.assertEqual(plan.order_by, "growth")


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = TrustworthyQueryEngine()

    def test_executes_verified_query(self):
        result = self.engine.run("统计2025年各医院每月基金支付金额及环比")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["rows"])
        self.assertEqual(result["trust"]["level"], "A")
        self.assertTrue(result["evidence"]["read_only"])

    def test_value_linking_and_top_n(self):
        result = self.engine.run("查询2025年三级甲等医院基金支付前2名")
        self.assertEqual(len(result["rows"]), 2)
        self.assertIn("3A", result["parameters"])

    def test_rejects_unknown_metric(self):
        with self.assertRaises(ValueError):
            self.engine.run("预测明年基金风险")

    def test_ast_validator_rejects_mutation(self):
        report = self.engine.validate("DELETE FROM settlement", [])
        self.assertTrue(report.errors)
        self.assertTrue(any("禁止" in error or "只读" in error for error in report.errors))

    def test_yoy_plan_generates_same_period_comparison(self):
        plan = understand(
            "统计下今年各医疗机构的住院医保基金使用情况，和同期进行比较，看哪个月的费用增长较高",
            date(2026, 8, 25),
        )
        tables = self.engine._required_tables(plan)
        sql, params = self.engine.compile_sql(plan, self.engine._join_plan(tables))
        self.assertIn("s.medical_type = '21'", sql)
        self.assertIn("same_period_value", sql)
        self.assertIn("yoy_rate", sql)
        self.assertIn("ORDER BY yoy_rate DESC", sql)
        self.assertEqual(params[:2], ["2025-01-01", "2026-08-25"])


if __name__ == "__main__":
    unittest.main()
