"""Backend Salary Calculation & Component Dependency Resolution Engine.

Acts as the authoritative source of truth for salary structure calculations,
resolving component dependency chains (e.g. HRA depends on Basic, Basic on Wage),
detecting circular dependencies, calculating PF, Professional Tax, Gross and Net pay.
"""
from core.exceptions import ValidationError


def calculate_salary_structure(
    monthly_wage: float,
    components_data: list,
    employee_pf_rate: float = 12.0,
    employer_pf_rate: float = 12.0,
    pf_base_component: str = "Basic Salary",
    professional_tax: float = 200.0,
    other_deductions: float = 0.0,
) -> dict:
    """Calculate full salary structure breakdown.

    Returns dict containing:
        monthly_wage, yearly_wage, components, gross_salary,
        employee_pf_amount, employer_pf_amount, professional_tax,
        other_deductions, total_deductions, net_salary.
    """
    try:
        monthly_wage = float(monthly_wage or 0)
        if monthly_wage <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError("Monthly wage must be greater than zero.", details={"monthly_wage": "Must be > 0."})

    yearly_wage = monthly_wage * 12.0

    # Parse components into working dictionary structures
    parsed_components = []
    for raw in components_data:
        c = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        calc_type = str(c.get("calculation_type", "PERCENTAGE")).upper()
        value = float(c.get("value", 0.0) or 0.0)
        depends_on = str(c.get("depends_on", "WAGE")).strip() or "WAGE"
        is_remainder = bool(c.get("is_fixed_allowance_remainder", False)) or (name.lower() == "fixed allowance")

        parsed_components.append({
            "name": name,
            "calculation_type": calc_type,
            "value": value,
            "depends_on": depends_on,
            "is_fixed_allowance_remainder": is_remainder,
            "calculated_amount": 0.0,
            "_resolved": False,
        })

    resolved_amounts = {"WAGE": monthly_wage}
    unresolved = [c for c in parsed_components if not c["is_fixed_allowance_remainder"]]

    # Pass-based resolution loop to resolve dependency chains
    max_passes = len(unresolved) + 2
    for _ in range(max_passes):
        if not unresolved:
            break
        progress = False
        still_unresolved = []

        for comp in unresolved:
            dep = comp["depends_on"]
            if dep in resolved_amounts:
                base_val = resolved_amounts[dep]
                if comp["calculation_type"] == "PERCENTAGE":
                    comp["calculated_amount"] = round((comp["value"] / 100.0) * base_val, 2)
                else:
                    comp["calculated_amount"] = round(comp["value"], 2)

                comp["_resolved"] = True
                resolved_amounts[comp["name"]] = comp["calculated_amount"]
                progress = True
            else:
                still_unresolved.append(comp)

        unresolved = still_unresolved

    if unresolved:
        cycle_names = ", ".join(c["name"] for c in unresolved)
        raise ValidationError(
            f"Circular dependency detected in salary components ({cycle_names}).",
            details={"components": "Components depend on each other cyclically."},
        )

    # Calculate fixed allowance / remainder component if present
    remainder_comps = [c for c in parsed_components if c["is_fixed_allowance_remainder"]]
    if remainder_comps:
        sum_other = sum(c["calculated_amount"] for c in parsed_components if not c["is_fixed_allowance_remainder"])
        rem_amount = max(0.0, round(monthly_wage - sum_other, 2))
        for r_comp in remainder_comps:
            r_comp["calculated_amount"] = rem_amount
            r_comp["_resolved"] = True
            resolved_amounts[r_comp["name"]] = rem_amount

    # Gross salary calculation
    gross_salary = sum(c["calculated_amount"] for c in parsed_components)

    # PF calculation
    pf_base_val = resolved_amounts.get(pf_base_component, resolved_amounts.get("Basic Salary", monthly_wage))
    employee_pf_amount = round((float(employee_pf_rate or 0) / 100.0) * pf_base_val, 2)
    employer_pf_amount = round((float(employer_pf_rate or 0) / 100.0) * pf_base_val, 2)

    prof_tax = round(float(professional_tax or 0), 2)
    other_ded = round(float(other_deductions or 0), 2)
    total_deductions = round(employee_pf_amount + prof_tax + other_ded, 2)
    net_salary = max(0.0, round(gross_salary - total_deductions, 2))

    # Clean working flags from component list
    final_components = []
    for c in parsed_components:
        c_copy = dict(c)
        c_copy.pop("_resolved", None)
        final_components.append(c_copy)

    return {
        "monthly_wage": round(monthly_wage, 2),
        "yearly_wage": round(yearly_wage, 2),
        "components": final_components,
        "gross_salary": round(gross_salary, 2),
        "employee_pf_rate": float(employee_pf_rate or 0),
        "employer_pf_rate": float(employer_pf_rate or 0),
        "pf_base_component": pf_base_component,
        "employee_pf_amount": employee_pf_amount,
        "employer_pf_amount": employer_pf_amount,
        "professional_tax": prof_tax,
        "other_deductions": other_ded,
        "total_deductions": total_deductions,
        "net_salary": net_salary,
    }
