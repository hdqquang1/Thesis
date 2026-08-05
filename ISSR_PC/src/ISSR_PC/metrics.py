"""Segmentation metrics: confusion matrix, per-class IoU, mIoU, overall accuracy (Day 10, [CC]).

Usage as a script:
    python -m vrseg.metrics gt.npy pred.npy [--num-classes 4]

gt.npy / pred.npy are integer label arrays of equal length. Points with a
ground-truth label outside [0, num_classes) are ignored (e.g. 31 = unlabelled).
"""

import argparse
import numpy as np

CLASS_NAMES = ["foliage", "stem", "ground", "undergrowth"]


def confusion_matrix(gt, pred, num_classes):
    """Rows = ground truth, columns = prediction."""
    gt = np.asarray(gt).astype(np.int64).ravel()
    pred = np.asarray(pred).astype(np.int64).ravel()
    if gt.shape != pred.shape:
        raise ValueError(f"gt and pred lengths differ: {gt.shape} vs {pred.shape}")
    valid = (gt >= 0) & (gt < num_classes)
    return np.bincount(
        num_classes * gt[valid] + pred[valid], minlength=num_classes * num_classes
    ).reshape(num_classes, num_classes)


def iou_per_class(cm):
    """IoU per class; NaN for classes absent from both gt and pred."""
    tp = np.diag(cm).astype(np.float64)
    denom = cm.sum(axis=0) + cm.sum(axis=1) - tp
    with np.errstate(invalid="ignore"):
        return np.where(denom > 0, tp / denom, np.nan)


def miou(cm):
    """Mean IoU over classes present in gt or pred (NaN classes excluded)."""
    return float(np.nanmean(iou_per_class(cm)))


def overall_accuracy(cm):
    return float(np.diag(cm).sum() / cm.sum())


def report(gt, pred, num_classes=4, class_names=None):
    """Return the metrics as a printable string."""
    names = class_names or CLASS_NAMES[:num_classes]
    names = [names[i] if i < len(names) else f"class{i}" for i in range(num_classes)]
    cm = confusion_matrix(gt, pred, num_classes)
    ious = iou_per_class(cm)

    width = max(len(n) for n in names) + 2
    lines = ["Per-class IoU:"]
    for name, iou in zip(names, ious):
        val = f"{iou:.4f}" if not np.isnan(iou) else "n/a (absent)"
        lines.append(f"  {name:<{width}}{val}")
    lines.append(f"mIoU:             {miou(cm):.4f}")
    lines.append(f"Overall accuracy: {overall_accuracy(cm):.4f}")
    lines.append("")
    lines.append("Confusion matrix (rows = ground truth, cols = prediction):")
    header = " " * width + "".join(f"{n[:8]:>10}" for n in names)
    lines.append(header)
    for name, row in zip(names, cm):
        lines.append(f"  {name:<{width - 2}}" + "".join(f"{v:>10}" for v in row))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gt", help="Ground-truth labels (.npy, int)")
    parser.add_argument("pred", help="Predicted labels (.npy, int)")
    parser.add_argument("--num-classes", type=int, default=4)
    args = parser.parse_args()
    print(report(np.load(args.gt), np.load(args.pred), args.num_classes))


if __name__ == "__main__":
    main()
