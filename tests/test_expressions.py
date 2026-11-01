# SPDX-License-Identifier: LGPL-2.1-or-later
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cobench.core.expressions import references, rewrite  # noqa: E402

NAMES = {"Socle", "Course", "Ecrou"}
LABELS = {"Socle", "Course", "Écrou"}


def r(text):
    return rewrite(text, NAMES, LABELS, "Variables")


def test_simple_reference():
    assert r("Socle.Largeur + 2 mm") == "Variables#Socle.Largeur + 2 mm"


def test_function_arguments_and_several_references():
    assert r("min(Course.Visee; Socle.Haut - 3)") == "min(Variables#Course.Visee; Variables#Socle.Haut - 3)"


def test_label_reference():
    assert r("<<Écrou>>.Diam / 2") == "Variables#<<Écrou>>.Diam / 2"


def test_unrelated_names_untouched():
    for text in ("Sketch.Constraints.L", "Pad.Length", "SocleBis.X", "My_Socle.X", "Pad001.Socle"):
        assert r(text) == text


def test_already_external_untouched():
    assert r("Variables#Socle.Largeur") == "Variables#Socle.Largeur"
    assert r("Other#<<Écrou>>.Diam") == "Other#<<Écrou>>.Diam"


def test_name_without_property_untouched():
    assert r("Socle") == "Socle"


def test_numbers_and_units():
    assert r("1e3 mm + Socle.L * 2.5") == "1e3 mm + Variables#Socle.L * 2.5"


def test_references():
    assert references("abs((Socle.A) - (Course.B))", NAMES, LABELS)
    assert not references("Pad.Length * 2", NAMES, LABELS)
