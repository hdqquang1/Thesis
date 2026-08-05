import numpy as np
import pytest

from vrseg.metrics import confusion_matrix, iou_per_class, miou, overall_accuracy


def test_perfect_prediction():
    gt = np.array([0, 1, 2, 3, 0, 1])
    cm = confusion_matrix(gt, gt, num_classes=4)
    assert np.array_equal(np.diag(cm), [2, 2, 1, 1])
    assert cm.sum() == len(gt)
    assert miou(cm) == 1.0
    assert overall_accuracy(cm) == 1.0


def test_hand_computed_case():
    # gt: three 0s, one 1. pred: gets two 0s right, calls one 0 a 1, gets the 1 right.
    gt = np.array([0, 0, 0, 1])
    pred = np.array([0, 0, 1, 1])
    cm = confusion_matrix(gt, pred, num_classes=2)
    assert np.array_equal(cm, [[2, 1], [0, 1]])
    ious = iou_per_class(cm)
    # class 0: tp=2, fp=0, fn=1 -> 2/3.  class 1: tp=1, fp=1, fn=0 -> 1/2.
    assert ious[0] == pytest.approx(2 / 3)
    assert ious[1] == pytest.approx(1 / 2)
    assert miou(cm) == pytest.approx((2 / 3 + 1 / 2) / 2)
    assert overall_accuracy(cm) == pytest.approx(3 / 4)


def test_absent_class_is_nan_and_excluded_from_miou():
    # Class 3 never appears in gt or pred.
    gt = np.array([0, 1, 2])
    pred = np.array([0, 1, 2])
    cm = confusion_matrix(gt, pred, num_classes=4)
    ious = iou_per_class(cm)
    assert np.isnan(ious[3])
    assert miou(cm) == 1.0


def test_invalid_gt_labels_ignored():
    # 31 = unlabelled points; they must not count anywhere.
    gt = np.array([0, 1, 31, 31])
    pred = np.array([0, 1, 2, 3])
    cm = confusion_matrix(gt, pred, num_classes=4)
    assert cm.sum() == 2
    assert overall_accuracy(cm) == 1.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion_matrix(np.zeros(3), np.zeros(4), num_classes=4)
