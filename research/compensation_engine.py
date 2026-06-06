class CompensationEngine:

    def evaluate(self, hard: dict, soft: dict, technical: dict) -> dict:
        """
        hard  — תוצאות H1/H6/H3/H4/H5 (בוליאני)
        soft  — תוצאות T2/T3/T4/T5/DIST/VOLDRY (בוליאני)
        technical — מדדים גולמיים: vcp_c, vol_dry_ratio, rs_63,
                    base_days, ext20, sma200_slope
        """

        # ── HARD RULES — פסילה מיידית ──
        if not hard.get("T1"):
            return self._reject("H_HARD: Price below SMA200")
        if not hard.get("T6"):
            return self._reject("H_HARD: SMA200 declining — Stage 4")
        if hard.get("gap_up", 0) > 0.05:
            return self._reject("H4_HARD: Gap >5%")
        if hard.get("avg_vol", 999999) < 200_000:
            return self._reject("H5_HARD: AvgVol <200K")
        if (hard.get("ext20", 0) > 0.15 or hard.get("ext50", 0) > 0.15) and hard.get("eps_growth", 0) < 0.30:
            return self._reject("H6_HARD: Extension >15%")
        if hard.get("vcp_c", 0) < 2 and hard.get("eps_growth", 0) < 0.30:
            return self._reject("H3_HARD: VCP c<2, no Hyper-Growth bypass")

        # ── SOFT RULES — פיצוי דינמי ──
        violations = []
        compensations = []

        vcp_c         = technical.get("vcp_c", 0)
        vol_dry       = technical.get("vol_dry_ratio", 1.0)
        rs_63         = technical.get("rs_63", 0)
        base_days     = technical.get("base_days", 0)
        ext20         = technical.get("ext20", 1.0)
        sma200_slope  = technical.get("sma200_slope", 0)

        # T2
        if not soft.get("T2", True):
            violations.append("T2")
            if vcp_c >= 3 and vol_dry < 0.50:
                compensations.append("T2_COMP: VCP≥3 + VolDry<50%")

        # T4
        if not soft.get("T4", True):
            violations.append("T4")
            if base_days >= 30 and ext20 < 0.08:
                compensations.append("T4_COMP: Base≥30d + Ext<8%")

        # T5
        if not soft.get("T5", True):
            violations.append("T5")
            if sma200_slope > 0.5:
                compensations.append("T5_COMP: SMA200 slope strong")

        # Distance from 52W High
        if not soft.get("dist_ok", True):
            violations.append("DIST")
            if rs_63 > 20 and vcp_c >= 3:
                compensations.append("DIST_COMP: RS63>20 + VCP≥3")
            elif hard.get("eps_growth", 0) >= 0.30:
                compensations.append("DIST_COMP: Hyper-Growth bypass (EPS>30%)")

        # Volume Dry-Up
        if not soft.get("vol_dry_ok", True):
            violations.append("VOLDRY")
            if ext20 < 0.05 and base_days >= 25:
                compensations.append("VOLDRY_COMP: Ext<5% + Base>=25d")
            elif technical.get("internal_vol_trend", 1.0) < 0.90 and technical.get("vol_dry_ratio", 1.0) < 1.15:
                compensations.append("VOLDRY_COMP: Internal vol declining + ratio contained")
            elif hard.get("eps_growth", 0) >= 0.30:
                compensations.append("VOLDRY_COMP: Hyper-Growth bypass (EPS>30%)")

        # ── VERDICT ──
        uncompensated = len(violations) - len(compensations)

        if uncompensated == 0:
            verdict = "PASS"
        elif uncompensated == 1 and len(compensations) >= 2:
            verdict = "WATCHLIST"
        else:
            verdict = f"REJECT_SOFT: {uncompensated} uncompensated violations"

        return {
            "verdict": verdict,
            "violations": violations,
            "compensations": compensations,
            "uncompensated": uncompensated,
        }

    def _reject(self, reason: str) -> dict:
        return {
            "verdict": f"REJECT_HARD",
            "reason": reason,
            "violations": [],
            "compensations": [],
            "uncompensated": 0,
        }
