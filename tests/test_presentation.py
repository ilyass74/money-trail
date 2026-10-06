from pathlib import Path
from decimal import Decimal
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.presentation import summary,timeline,money,pill


class PresentationTests(unittest.TestCase):
    def test_unknown_is_never_displayed_as_zero(self):
        self.assertEqual(money(None),'Inconnu')
        self.assertEqual(money(Decimal('0.00')),'0,00 MAD')

    def test_discrepancy_copy_does_not_invent_cause(self):
        d={'kind':'settlement','result':dict(status='ecart',expected_amount=Decimal('880.00'),received_amount=Decimal('850.00'),difference=Decimal('-30.00'))}
        text=summary(d)
        self.assertIn('880,00 MAD',text);self.assertIn('850,00 MAD',text);self.assertIn('-30,00 MAD',text)
        self.assertIn('doit être expliqué',text)

    def test_missing_fees_are_named(self):
        d={'kind':'settlement','result':dict(status='calcul_bloque',quality='donnees_incompletes'),
           'explanation':{'missing_sources':['fees']}}
        self.assertIn('frais',summary(d));self.assertIn('bloqué',summary(d))

    def test_history_escapes_actor_and_comment(self):
        events=[dict(actor='<img src=x>',action='comment',revision=2,occurred_at='2026-10-05',details={'note':'<script>alert(1)</script>'})]
        html=timeline(events)
        self.assertNotIn('<script>',html);self.assertNotIn('<img',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('Commentaire ajouté',html)
        self.assertNotIn('<script>',pill('<script>'))


if __name__=='__main__':unittest.main()
