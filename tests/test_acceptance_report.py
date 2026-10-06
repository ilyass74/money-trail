"""Un rapport de recette ne doit pas confondre succès, absence et rejet."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from acceptance import acceptance_matrix


class AcceptanceReportTests(unittest.TestCase):
    def test_no_execution_cannot_validate_any_criterion(self):
        matrix=acceptance_matrix([])
        self.assertEqual(len(matrix),18)
        self.assertFalse(any(row['status']=='validated_current_contract' for row in matrix))
        self.assertEqual(next(row for row in matrix if row['id']=='A17')['status'],'not_run')

    def test_failure_is_not_hidden_by_passing_reference(self):
        group={'tests':[{'id':'engine.test_C01_reference','status':'passed'},
                        {'id':'engine.test_C39_missing_bank_deadline','status':'failed'}]}
        matrix=acceptance_matrix([group])
        self.assertEqual(next(row for row in matrix if row['id']=='A08')['status'],'failed')

    def test_skipped_restoration_is_not_validated(self):
        group={'tests':[{'id':'engine.test_D06_backup_and_restore_in_isolated_database','status':'skipped'}]}
        matrix=acceptance_matrix([group])
        self.assertEqual(next(row for row in matrix if row['id']=='A16')['status'],'not_run')
