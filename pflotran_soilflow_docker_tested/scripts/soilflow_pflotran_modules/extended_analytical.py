from __future__ import annotations

import math


def exp1_numeric(u: float) -> float:
    u = max(u, 1.0e-10)
    upper = max(80.0, u + 80.0)
    n = 4000
    if n % 2:
        n += 1
    h = (upper - u) / n

    def f(x: float) -> float:
        return math.exp(-x) / x

    total = f(u) + f(upper)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * f(u + i * h)
    return total * h / 3.0


def green_ampt_cumulative_infiltration(time_s: float, ksat_m_s: float, suction_m: float, delta_theta: float) -> float:
    cap = max(1.0e-12, suction_m * delta_theta)
    target = ksat_m_s * time_s
    low, high = 0.0, max(cap, target + cap)

    def residual(value: float) -> float:
        return value - cap * math.log1p(value / cap) - target

    while residual(high) < 0:
        high *= 2.0
    for _ in range(80):
        mid = 0.5 * (low + high)
        if residual(mid) < 0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def buckley_fractional_flow(sw: float, swc: float, sor: float, mu_w: float, mu_o: float) -> float:
    se = max(0.0, min(1.0, (sw - swc) / (1.0 - swc - sor)))
    krw = se**2
    kro = (1.0 - se) ** 2
    if krw == 0.0:
        return 0.0
    return (krw / mu_w) / (krw / mu_w + kro / mu_o)


def generate_extended_analytical_rows(test_name: str) -> tuple[list[dict[str, float]], str, str, str, str]:
    rows: list[dict[str, float]] = []
    if test_name == "theis_radial_flow":
        transmissivity = 1.0e-3
        storage = 1.0e-4
        pumping_rate = 1.0e-3
        time_s = 86400.0
        for i in range(1, 101):
            radius = 1.0 + 2.0 * i
            u = radius * radius * storage / (4.0 * transmissivity * time_s)
            drawdown = pumping_rate * exp1_numeric(u) / (4.0 * math.pi * transmissivity)
            rows.append({"radius_m": radius, "u": u, "drawdown_m": drawdown})
        return rows, "radius_m", "drawdown_m", "Theis radial groundwater flow", "Theis: s(r,t)=Q/(4*pi*T)*W(u), u=r^2*S/(4*T*t)."
    if test_name == "ogata_banks_1d_transport":
        velocity = 1.0
        dispersion = 0.1
        time_s = 10.0
        c0 = 1.0
        for i in range(101):
            x = i * 0.2
            root = 2.0 * math.sqrt(dispersion * time_s)
            c = 0.5 * c0 * (
                math.erfc((x - velocity * time_s) / root)
                + math.exp(velocity * x / dispersion) * math.erfc((x + velocity * time_s) / root)
            )
            rows.append({"x_m": x, "concentration": c})
        return rows, "x_m", "concentration", "Ogata-Banks 1D transport", "Ogata-Banks для полуограниченной адвекции-дисперсии с постоянной входной концентрацией."
    if test_name == "terzaghi_1d_consolidation":
        cv = 1.0e-6
        height = 1.0
        u0 = 100.0
        time_s = 2.0e5
        for i in range(101):
            z = height * i / 100.0
            pressure = 0.0
            for m in range(50):
                n = 2 * m + 1
                pressure += (4.0 * u0 / (math.pi * n)) * math.sin(n * math.pi * z / height) * math.exp(
                    -(n * math.pi / height) ** 2 * cv * time_s
                )
            rows.append({"z_m": z, "excess_pore_pressure_kpa": pressure})
        return rows, "z_m", "excess_pore_pressure_kpa", "Terzaghi 1D consolidation", "Рядовое решение Terzaghi для одномерной консолидации с дренированными границами."
    if test_name == "philip_infiltration":
        sorptivity = 0.012
        a_coeff = 2.0e-6
        for i in range(1, 101):
            time_s = i * 600.0
            infiltration = sorptivity * math.sqrt(time_s) + a_coeff * time_s
            rate = 0.5 * sorptivity / math.sqrt(time_s) + a_coeff
            rows.append({"time_s": time_s, "cumulative_infiltration_m": infiltration, "infiltration_rate_m_s": rate})
        return rows, "time_s", "cumulative_infiltration_m", "Philip infiltration", "Полуаналитическое приближение Philip: I(t)=S*sqrt(t)+A*t."
    if test_name == "green_ampt_infiltration":
        ksat = 1.0e-6
        suction = 0.25
        delta_theta = 0.25
        for i in range(1, 101):
            time_s = i * 900.0
            infiltration = green_ampt_cumulative_infiltration(time_s, ksat, suction, delta_theta)
            rows.append({"time_s": time_s, "cumulative_infiltration_m": infiltration})
        return rows, "time_s", "cumulative_infiltration_m", "Green-Ampt infiltration", "Неявное аналитическое решение Green-Ampt для резкого фронта инфильтрации."
    if test_name == "heat_conduction_1d":
        diffusivity = 1.0e-6
        time_s = 86400.0
        t_initial = 10.0
        t_surface = 20.0
        for i in range(101):
            x = i * 0.02
            temp = t_initial + (t_surface - t_initial) * math.erfc(x / (2.0 * math.sqrt(diffusivity * time_s)))
            rows.append({"x_m": x, "temperature_c": temp})
        return rows, "x_m", "temperature_c", "1D heat conduction", "erfc-решение теплопроводности для полуограниченного тела со ступенчатой температурой поверхности."
    if test_name == "buckley_leverett":
        swc, sor, mu_w, mu_o = 0.2, 0.2, 1.0, 5.0
        for i in range(101):
            sw = swc + (1.0 - swc - sor) * i / 100.0
            fw = buckley_fractional_flow(sw, swc, sor, mu_w, mu_o)
            rows.append({"water_saturation": sw, "fractional_flow": fw})
        return rows, "water_saturation", "fractional_flow", "Buckley-Leverett displacement", "Фракционный поток Corey/Buckley-Leverett для несмешивающегося вытеснения."
    if test_name == "richards_mms":
        length = 1.0
        h0 = -1.0
        amplitude = 0.2
        time_days = 0.5
        tau = 1.0
        for i in range(101):
            z = length * i / 100.0
            head = h0 + amplitude * math.sin(math.pi * z / length) * math.exp(-time_days / tau)
            rows.append({"z_m": z, "pressure_head_m": head})
        return rows, "z_m", "pressure_head_m", "Richards manufactured solution", "MMS-профиль h(z,t)=h0+A*sin(pi*z/L)*exp(-t/tau); source term выводится из выбранной формы h."
    if test_name == "boussinesq_groundwater_mound":
        length = 100.0
        h0 = 10.0
        amplitude = 1.0
        diffusivity = 20.0
        time_days = 10.0
        for i in range(101):
            x = length * i / 100.0
            head = h0 + amplitude * math.sin(math.pi * x / length) * math.exp(diffusivity * -((math.pi / length) ** 2) * time_days)
            rows.append({"x_m": x, "water_table_head_m": head})
        return rows, "x_m", "water_table_head_m", "Boussinesq groundwater mound", "Линеаризованное решение Boussinesq: синусоидальный бугор уровня грунтовых вод затухает диффузионно."
    raise ValueError(f"Unknown extended analytical test: {test_name}")


def generate_normalized_profile_rows(test_name: str, length_m: float = 1.2) -> list[dict[str, float]]:
    rows, _x_key, y_key, _title, _analytical_note = generate_extended_analytical_rows(test_name)
    values = [float(row[y_key]) for row in rows if y_key in row]
    value_min = min(values)
    value_span = max(max(values) - value_min, 1.0e-12)
    profile_rows: list[dict[str, float]] = []
    for index, row in enumerate(rows):
        depth_m = length_m * index / max(1, len(rows) - 1)
        normalized = (float(row[y_key]) - value_min) / value_span
        profile_rows.append(
            {
                "depth_m": depth_m,
                "theta_m3_m3": 0.18 + 0.22 * normalized,
                "pressure_head_m": -1.2 + 0.8 * normalized,
            }
        )
    return profile_rows
