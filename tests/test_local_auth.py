from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.local_auth import hash_password,verify_password,authorize,username
from money_trail.workflow import WorkflowError


class LocalAuthTests(unittest.TestCase):
    def test_password_is_salted_and_verifiable(self):
        password='fixture-password-only'
        first=hash_password(password);second=hash_password(password)
        self.assertNotEqual(first,second)
        self.assertNotIn(password,first)
        self.assertTrue(verify_password(password,first))
        self.assertFalse(verify_password('wrong-password',first))

    def test_invalid_hash_and_short_password(self):
        self.assertFalse(verify_password('any','broken'))
        with self.assertRaises(WorkflowError):hash_password('short')

    def test_viewer_cannot_write(self):
        for verb in ('start','comment','propose','approve','reject','close','sync'):
            with self.assertRaises(WorkflowError):authorize('viewer',verb)

    def test_roles_separate_proposal_and_validation(self):
        authorize('analyst','propose');authorize('reviewer','approve')
        with self.assertRaises(WorkflowError):authorize('analyst','approve')
        with self.assertRaises(WorkflowError):authorize('reviewer','propose')

    def test_username_normalized(self):
        self.assertEqual(username(' Ilyass '),'ilyass')
        with self.assertRaises(WorkflowError):username('../someone')


if __name__=='__main__':unittest.main()
