"""
Fon Öngörü Strateji Motoru
Momentum, Varlık Rotasyonu, Risk-Getiri ve Tutarlılık analizleri ile
composite öngörü skoru hesaplar.
"""
import math


class StrategyEngine:
    """Fon öngörü ve rotasyon stratejisi motoru"""

    # Piyasa rejimi sabitleri
    REGIME_RISK_ON = "risk_on"       # Hisse ağırlıklı
    REGIME_DEFENSIVE = "defensive"   # Altın/Tahvil ağırlıklı
    REGIME_INFLATION = "inflation"   # Döviz/Altın ağırlıklı
    REGIME_NEUTRAL = "neutral"       # Dengeli

    # Varlık sınıfı anahtar kelime eşlemeleri
    ASSET_CLASS_KEYWORDS = {
        "hisse": ["Hisse Senedi", "Pay Senedi", "Hisse"],
        "tahvil": ["Devlet Tahvili", "Özel Sektör Tahvili", "Borçlanma Araçları",
                   "Eurobond", "Kamu Borçlanma", "Özel Sektör Borçlanma",
                   "Kira Sertifikaları", "Kamu Kira Sertifika"],
        "altin": ["Kıymetli Madenler", "Altın", "Kıymetli Maden"],
        "doviz": ["Döviz", "YP Cinsinden", "Yabancı Para"],
        "repo": ["Repo", "Ters Repo", "Katılma Hesabı", "Mevduat"],
        "fon": ["Yatırım Fonları", "Borsa Yatırım Fonları", "BYF"],
    }

    # Rejime göre varlık sınıfı ağırlıkları
    REGIME_WEIGHTS = {
        REGIME_RISK_ON: {
            "hisse": 0.40, "tahvil": 0.10, "altin": 0.10,
            "doviz": 0.05, "repo": 0.05, "fon": 0.30,
        },
        REGIME_DEFENSIVE: {
            "hisse": 0.05, "tahvil": 0.30, "altin": 0.35,
            "doviz": 0.10, "repo": 0.15, "fon": 0.05,
        },
        REGIME_INFLATION: {
            "hisse": 0.10, "tahvil": 0.10, "altin": 0.30,
            "doviz": 0.30, "repo": 0.05, "fon": 0.15,
        },
        REGIME_NEUTRAL: {
            "hisse": 0.20, "tahvil": 0.20, "altin": 0.20,
            "doviz": 0.10, "repo": 0.10, "fon": 0.20,
        },
    }

    # Composite skor ağırlıkları (rejime göre)
    COMPOSITE_WEIGHTS = {
        REGIME_RISK_ON: {
            "momentum": 0.40, "rotation": 0.25,
            "risk_return": 0.20, "consistency": 0.15,
        },
        REGIME_DEFENSIVE: {
            "momentum": 0.25, "rotation": 0.40,
            "risk_return": 0.20, "consistency": 0.15,
        },
        REGIME_INFLATION: {
            "momentum": 0.30, "rotation": 0.35,
            "risk_return": 0.20, "consistency": 0.15,
        },
        REGIME_NEUTRAL: {
            "momentum": 0.35, "rotation": 0.30,
            "risk_return": 0.20, "consistency": 0.15,
        },
    }

    REGIME_LABELS = {
        REGIME_RISK_ON: ("🟢 Risk-On", "Hisse ağırlıklı fonlar öne çıkar"),
        REGIME_DEFENSIVE: ("🔴 Defansif", "Altın/Tahvil fonları öne çıkar"),
        REGIME_INFLATION: ("🟡 Enflasyon Koruması", "Döviz/Altın fonları öne çıkar"),
        REGIME_NEUTRAL: ("⚪ Nötr", "Dengeli dağılım önerilir"),
    }

    def __init__(self):
        self._regime = self.REGIME_NEUTRAL
        self._regime_detail = {}

    # ──────────────────────────────────────
    # Piyasa Rejimi Tespiti
    # ──────────────────────────────────────

    def detect_regime(self, macro_data):
        """Makro verilerden piyasa rejimini tespit et.

        Args:
            macro_data: {name: {price, daily, monthly, quarterly}} dict

        Returns:
            (regime_key, detail_dict)
        """
        if not macro_data:
            self._regime = self.REGIME_NEUTRAL
            self._regime_detail = {"reason": "Makro veri yok"}
            return self._regime, self._regime_detail

        bist = macro_data.get("BIST-100", {})
        gold = macro_data.get("Altın", {})
        usd = macro_data.get("USD/TRY", {})

        bist_m = bist.get("monthly", 0) or 0
        gold_m = gold.get("monthly", 0) or 0
        usd_m = usd.get("monthly", 0) or 0

        bist_d = bist.get("daily", 0) or 0
        gold_d = gold.get("daily", 0) or 0
        usd_d = usd.get("daily", 0) or 0

        detail = {
            "bist_monthly": bist_m,
            "gold_monthly": gold_m,
            "usd_monthly": usd_m,
            "bist_daily": bist_d,
            "gold_daily": gold_d,
            "usd_daily": usd_d,
        }

        # Puanlama sistemi
        risk_on_score = 0
        defensive_score = 0
        inflation_score = 0

        # BIST sinyalleri
        if bist_m > 5:
            risk_on_score += 3
        elif bist_m > 2:
            risk_on_score += 2
        elif bist_m > 0:
            risk_on_score += 1
        elif bist_m < -5:
            defensive_score += 3
        elif bist_m < -2:
            defensive_score += 2
        elif bist_m < 0:
            defensive_score += 1

        # Altın sinyalleri
        if gold_m > 5:
            defensive_score += 2
            inflation_score += 1
        elif gold_m > 2:
            defensive_score += 1

        # USD/TRY sinyalleri
        if usd_m > 5:
            inflation_score += 3
        elif usd_m > 3:
            inflation_score += 2
        elif usd_m > 1:
            inflation_score += 1

        # Günlük ivme bonusu
        if bist_d > 1:
            risk_on_score += 1
        if gold_d > 1:
            defensive_score += 1
        if usd_d > 0.5:
            inflation_score += 1

        scores = {
            self.REGIME_RISK_ON: risk_on_score,
            self.REGIME_DEFENSIVE: defensive_score,
            self.REGIME_INFLATION: inflation_score,
        }

        detail["regime_scores"] = scores

        max_score = max(scores.values())
        if max_score <= 1:
            regime = self.REGIME_NEUTRAL
        else:
            regime = max(scores, key=scores.get)

        self._regime = regime
        self._regime_detail = detail
        return regime, detail

    def get_regime_label(self):
        """Mevcut rejim etiketini döndür"""
        return self.REGIME_LABELS.get(self._regime, ("⚪ Nötr", ""))

    # ──────────────────────────────────────
    # Momentum Analizi
    # ──────────────────────────────────────

    def calculate_momentum(self, row):
        """Tek bir fon satırı için momentum skorunu hesapla.
        0 değerli dönemler (veri yok) hesaplamadan hariç tutulur.

        Args:
            row: DataFrame satırı (1 Ay (%), 3 Ay (%), ...)

        Returns:
            dict: {short_momentum, long_momentum, acceleration, consistency_bonus, total,
                   available_periods, total_periods}
        """
        m1 = self._safe_float(row.get("1 Ay (%)", 0))
        m3 = self._safe_float(row.get("3 Ay (%)", 0))
        m6 = self._safe_float(row.get("6 Ay (%)", 0))
        y1 = self._safe_float(row.get("1 Yıl (%)", 0))
        y3 = self._safe_float(row.get("3 Yıl (%)", 0))
        y5 = self._safe_float(row.get("5 Yıl (%)", 0))

        # Kısa vadeli momentum — sadece verisi olan dönemler
        short_parts = []
        short_weights = []
        if m1 != 0:
            short_parts.append(m1)
            short_weights.append(0.4)
        if m3 != 0:
            short_parts.append(m3)
            short_weights.append(0.3)
        if m6 != 0:
            short_parts.append(m6)
            short_weights.append(0.3)

        if short_parts and sum(short_weights) > 0:
            # Ağırlıkları normalize et
            w_sum = sum(short_weights)
            short_mom = sum(v * w / w_sum for v, w in zip(short_parts, short_weights))
        else:
            short_mom = 0

        # Uzun vadeli momentum — sadece verisi olan dönemler
        long_parts = []
        long_weights = []
        if y1 != 0:
            long_parts.append(y1)
            long_weights.append(0.5)
        if y3 != 0:
            y3_annual = y3 / 3
            long_parts.append(y3_annual)
            long_weights.append(0.3)
        if y5 != 0:
            y5_annual = y5 / 5
            long_parts.append(y5_annual)
            long_weights.append(0.2)

        if long_parts and sum(long_weights) > 0:
            w_sum = sum(long_weights)
            long_mom = sum(v * w / w_sum for v, w in zip(long_parts, long_weights))
        else:
            long_mom = 0

        # Momentum ivmesi
        m3_monthly = m3 / 3 if m3 != 0 else 0
        if abs(m3_monthly) > 0.001 and m1 != 0:
            acceleration = m1 / m3_monthly
        else:
            acceleration = 1.0
        acceleration = max(0.1, min(acceleration, 5.0))

        # Tutarlılık bonusu — sadece verisi olan dönemleri say
        all_periods = [m1, m3, m6, y1, y3, y5]
        available_periods = [p for p in all_periods if p != 0]
        total_periods = len(available_periods)
        positive_count = sum(1 for p in available_periods if p > 0)

        # Oran bazlı bonus — 0 olanları saymadan
        if total_periods > 0:
            pos_ratio = positive_count / total_periods
            if pos_ratio >= 1.0:
                consistency_bonus = 1.25
            elif pos_ratio >= 0.83:  # ~5/6
                consistency_bonus = 1.15
            elif pos_ratio >= 0.67:  # ~4/6
                consistency_bonus = 1.10
            else:
                consistency_bonus = 1.0
        else:
            consistency_bonus = 1.0

        # Toplam momentum
        combined = short_mom * 0.6 + long_mom * 0.4
        total = combined * consistency_bonus

        return {
            "short_momentum": round(short_mom, 2),
            "long_momentum": round(long_mom, 2),
            "acceleration": round(acceleration, 2),
            "consistency_bonus": consistency_bonus,
            "positive_periods": positive_count,
            "total_periods": total_periods,
            "total": round(total, 2),
        }

    # ──────────────────────────────────────
    # Varlık Rotasyonu Puanı
    # ──────────────────────────────────────

    def calculate_rotation_score(self, allocation_data):
        """Fonun varlık dağılımını mevcut rejime göre puanla.

        Args:
            allocation_data: {varlık_adı: {percentage: float, color: str}}

        Returns:
            dict: {asset_breakdown, total}
        """
        if not allocation_data:
            return {"asset_breakdown": {}, "total": 0, "detail": "Varlık verisi yok"}

        # Varlık sınıflarını grupla
        asset_groups = {k: 0.0 for k in self.ASSET_CLASS_KEYWORDS}

        for asset_name, data in allocation_data.items():
            pct = data.get("percentage", 0) if isinstance(data, dict) else float(data)
            matched = False
            for group, keywords in self.ASSET_CLASS_KEYWORDS.items():
                for keyword in keywords:
                    if keyword.lower() in asset_name.lower():
                        asset_groups[group] += pct
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                # Eşleşmeyen varlıkları "fon" grubuna ekle
                asset_groups["fon"] += pct

        # Rejime göre ağırlıklarla puanla
        regime_weights = self.REGIME_WEIGHTS.get(self._regime, self.REGIME_WEIGHTS[self.REGIME_NEUTRAL])
        total_score = 0
        breakdown = {}

        for group, pct in asset_groups.items():
            weight = regime_weights.get(group, 0)
            score = pct * weight
            total_score += score
            if pct > 0:
                breakdown[group] = {
                    "percentage": round(pct, 1),
                    "weight": weight,
                    "score": round(score, 2),
                }

        return {
            "asset_breakdown": breakdown,
            "total": round(total_score, 2),
        }

    # ──────────────────────────────────────
    # Risk-Getiri Metrikleri
    # ──────────────────────────────────────

    def calculate_risk_return(self, row):
        """Risk-getiri metriklerini hesapla (Pseudo-Sharpe + Drawdown).
        0 değerli dönemler hariç tutulur.

        Args:
            row: DataFrame satırı

        Returns:
            dict: {avg_return, volatility, sharpe, max_drawdown, total}
        """
        m1 = self._safe_float(row.get("1 Ay (%)", 0))
        m3 = self._safe_float(row.get("3 Ay (%)", 0))
        m6 = self._safe_float(row.get("6 Ay (%)", 0))
        y1 = self._safe_float(row.get("1 Yıl (%)", 0))

        # Aylık normalize getiriler — sadece verisi olanlar
        returns = []
        if m1 != 0:
            returns.append(m1)
        if m3 != 0:
            returns.append(m3 / 3)
        if m6 != 0:
            returns.append(m6 / 6)
        if y1 != 0:
            returns.append(y1 / 12)

        avg_return = sum(returns) / len(returns) if returns else 0

        # Volatilite (standart sapma)
        if len(returns) > 1:
            variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = math.sqrt(variance)
        else:
            volatility = 0.001

        # Pseudo-Sharpe
        sharpe = avg_return / volatility if volatility > 0.001 else 0
        sharpe = max(-5, min(sharpe, 5))

        # Drawdown: verisi olan dönemler arası en büyük düşüş
        period_returns = [p for p in [m1, m3, m6, y1] if p != 0]
        if period_returns:
            max_val = max(period_returns)
            min_val = min(period_returns)
            max_drawdown = (max_val - min_val) / max(abs(max_val), 1)
        else:
            max_drawdown = 0

        total = sharpe * 10 - max_drawdown * 5

        return {
            "avg_return": round(avg_return, 2),
            "volatility": round(volatility, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_drawdown, 2),
            "total": round(total, 2),
        }

    # ──────────────────────────────────────
    # Tutarlılık Skoru
    # ──────────────────────────────────────

    def calculate_consistency(self, row):
        """Fon getirilerinin tutarlılığını ölç.
        0 değerli dönemler (veri yok) hariç tutulur.

        Returns:
            dict: {std_dev, trend_direction, total}
        """
        m1 = self._safe_float(row.get("1 Ay (%)", 0))
        m3 = self._safe_float(row.get("3 Ay (%)", 0))
        m6 = self._safe_float(row.get("6 Ay (%)", 0))
        y1 = self._safe_float(row.get("1 Yıl (%)", 0))

        # Aylık normalize — sadece verisi olanlar
        monthly = []
        if m1 != 0:
            monthly.append(m1)
        if m3 != 0:
            monthly.append(m3 / 3)
        if m6 != 0:
            monthly.append(m6 / 6)
        if y1 != 0:
            monthly.append(y1 / 12)

        avg = sum(monthly) / len(monthly) if monthly else 0

        if len(monthly) > 1:
            std_dev = math.sqrt(
                sum((r - avg) ** 2 for r in monthly) / (len(monthly) - 1)
            )
        else:
            std_dev = 0

        # Trend yönü: son dönemler önceki dönemlerden iyi mi?
        trend = 0
        if len(monthly) >= 2:
            if monthly[0] > monthly[-1]:
                trend = 1  # Son dönem daha iyi (hızlanma)
            elif monthly[0] < monthly[-1]:
                trend = -0.5  # Son dönem daha kötü (yavaşlama)

        # Düşük std_dev → yüksek tutarlılık → iyi
        consistency_score = max(0, 10 - std_dev * 2) + trend * 3

        return {
            "std_dev": round(std_dev, 2),
            "trend": trend,
            "avg_monthly": round(avg, 2),
            "total": round(consistency_score, 2),
        }

    # ──────────────────────────────────────
    # Composite Öngörü Skoru
    # ──────────────────────────────────────

    def calculate_forecast(self, row, allocation_data=None, macro_data=None):
        """Tek bir fon için composite öngörü skoru hesapla.

        Args:
            row: DataFrame satırı
            allocation_data: Fonun varlık dağılımı (opsiyonel)
            macro_data: Piyasa verileri (opsiyonel, rejim zaten belirlenmiş olabilir)

        Returns:
            dict: {momentum, rotation, risk_return, consistency, composite, regime, details}
        """
        # Eğer macro_data verilmişse rejimi güncelle
        if macro_data:
            self.detect_regime(macro_data)

        # Her bileşeni hesapla
        momentum = self.calculate_momentum(row)
        rotation = self.calculate_rotation_score(allocation_data or {})
        risk_return = self.calculate_risk_return(row)
        consistency = self.calculate_consistency(row)

        # Composite ağırlıklar (rejime göre)
        weights = self.COMPOSITE_WEIGHTS.get(
            self._regime, self.COMPOSITE_WEIGHTS[self.REGIME_NEUTRAL]
        )

        # Normalize: her bileşeni -100..+100 arası normalize et
        mom_norm = self._normalize(momentum["total"], -50, 100)
        rot_norm = self._normalize(rotation["total"], 0, 40)
        rr_norm = self._normalize(risk_return["total"], -30, 30)
        con_norm = self._normalize(consistency["total"], 0, 15)

        composite = (
            mom_norm * weights["momentum"]
            + rot_norm * weights["rotation"]
            + rr_norm * weights["risk_return"]
            + con_norm * weights["consistency"]
        )

        regime_label, regime_desc = self.get_regime_label()

        return {
            "momentum": momentum,
            "rotation": rotation,
            "risk_return": risk_return,
            "consistency": consistency,
            "composite": round(composite, 1),
            "regime": self._regime,
            "regime_label": regime_label,
            "regime_desc": regime_desc,
            "weights": weights,
            "normalized": {
                "momentum": round(mom_norm, 1),
                "rotation": round(rot_norm, 1),
                "risk_return": round(rr_norm, 1),
                "consistency": round(con_norm, 1),
            },
        }

    def calculate_all_forecasts(self, df, allocation_cache, macro_data):
        """Tüm fonlar için öngörü skoru hesapla.

        Args:
            df: Fon verileri DataFrame'i
            allocation_cache: {fon_kodu: allocation_data} dict
            macro_data: Piyasa verileri dict

        Returns:
            dict: {fon_kodu: forecast_result}
        """
        # Rejimi bir kez belirle
        self.detect_regime(macro_data)

        results = {}
        for _, row in df.iterrows():
            fon_kodu = str(row.get("Fon Kodu", "")).strip()
            if not fon_kodu:
                continue

            alloc = allocation_cache.get(fon_kodu, {})
            forecast = self.calculate_forecast(row, alloc)
            results[fon_kodu] = forecast

        return results

    def get_top_funds(self, forecasts, n=10):
        """En yüksek öngörü skoruna sahip N fonu döndür.

        Returns:
            list: [(fon_kodu, composite_score, forecast_detail), ...]
        """
        ranked = sorted(
            forecasts.items(),
            key=lambda x: x[1]["composite"],
            reverse=True,
        )
        return [(k, v["composite"], v) for k, v in ranked[:n]]

    # ──────────────────────────────────────
    # Yardımcı Fonksiyonlar
    # ──────────────────────────────────────

    @staticmethod
    def _safe_float(val):
        """Değeri güvenli float'a çevir"""
        try:
            if isinstance(val, (int, float)):
                return float(val)
            return float(str(val).replace(",", ".").replace("%", "").strip())
        except (ValueError, TypeError, AttributeError):
            return 0.0

    @staticmethod
    def _normalize(value, min_val, max_val):
        """Değeri 0-100 arasına normalize et"""
        if max_val == min_val:
            return 50.0
        normalized = (value - min_val) / (max_val - min_val) * 100
        return max(0, min(100, normalized))

