"""Plots FPS vs. visible point count from the UE5 point-budget benchmark."""

import matplotlib.pyplot as plt


def main() -> None:
    # Data from doc/UE5.md, "Point budget and FPS" table.
    # Cloud: labelled_native_forest_2, development laptop, Ultra Performance scaling.
    visible_points_m = [p / 1_000_000 for p in
                        [349_829, 999_325, 1_955_510, 3_993_753, 7_970_572, 15_999_997, 22_949_102]]
    fps = [60.01, 60.00, 60.00, 47.76, 34.46, 21.46, 17.24]

    # 350K and 1M are capped at the editor's 60 FPS limit, not genuine frame-rate
    # measurements (see doc/UE5.md caveat).
    capped = 2

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.set_xlabel("Visible points (millions)")
    ax.set_ylabel("FPS")
    ax.plot(visible_points_m[:capped], fps[:capped], color="tab:red", marker="s",
            linestyle="--", alpha=0.4, label="FPS (capped at 60)")
    ax.plot(visible_points_m[capped - 1:], fps[capped - 1:], color="tab:red", marker="s",
            label="FPS (genuine)")
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.suptitle("Point budget vs. FPS")
    fig.tight_layout()
    # plt.savefig("point_budget_fps.png", dpi=600)
    plt.show()


if __name__ == "__main__":
    main()
