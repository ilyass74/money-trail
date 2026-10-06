from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.workflow import transition,check_reviewer,actor_name,WorkflowError


class WorkflowRulesTests(unittest.TestCase):
    def test_proposal_requires_review(self):
        with self.assertRaises(WorkflowError):transition('open','propose')
        self.assertEqual(transition('in_review','propose'),'awaiting_validation')

    def test_self_validation_is_refused(self):
        with self.assertRaises(WorkflowError):check_reviewer(' Ilyass ','ILYASS')
        check_reviewer('Ilyass','reviewer-demo')

    def test_rejected_proposal_can_be_reworked(self):
        self.assertEqual(transition('rejected','start'),'in_review')

    def test_close_does_not_bypass_decision(self):
        for status in ('open','in_review','awaiting_validation'):
            with self.assertRaises(WorkflowError):transition(status,'close')
        self.assertEqual(transition('approved','close'),'closed')

    def test_closed_case_cannot_be_modified(self):
        for action in ('start','comment','propose','approve','reject','close'):
            with self.assertRaises(WorkflowError):transition('closed',action)

    def test_actor_required(self):
        with self.assertRaises(WorkflowError):actor_name('  ')


if __name__=='__main__':unittest.main()
