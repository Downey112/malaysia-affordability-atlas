"""Generate the Power BI Project (TMDL model and PBIR report) for the Affordability Atlas.

Run after the pipeline. Rewrites only the three AffordabilityAtlas paths under powerbi/.
"""
import json
import shutil
import uuid
from pathlib import Path

import pyarrow.parquet as pq

NAME = "AffordabilityAtlas"
BASKET = "'Staples + rice (17 items)'"
POSITION = "'P10: lower-income household'"
HOUSEHOLD = "'Married (2 Children)'"
MT = "AtlasMeasures"
ROOT = Path(__file__).resolve().parent.parent
PBI = ROOT / "powerbi"
PROCESSED_DIR = ROOT / "data" / "processed"
NS = uuid.UUID("3d8b2e5a-19fa-4c8d-b3e1-7a4c9f0e2b6d")
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"

BLUE = "#1D4ED8"
MUTED = "#64748B"
INK = "#0F172A"
SERIES = [BLUE, "#94A3B8", "#CBD5E1", "#0284C7", MUTED, "#334155"]

PCT = "0.0\\%"
SIGNED = "+0.0\\%;-0.0\\%;0.0\\%"
RM0 = "\\R\\M#,0"
RM2 = "\\R\\M#,0.00"
TIMES = "0.00\\x"

TABLES = [
    "dim_state", "dim_basket", "dim_income_position", "dim_household_type", "dim_spending_group",
    "mart_burden", "mart_counterfactual", "mart_decomposition", "mart_budget_gap", "mart_pli",
    "mart_pressure", "mart_real_income", "mart_real_wages", "fact_state_year", "fact_district_year",
    "fact_spending_state", "fact_basket_state",
]

FACT_KEY_COLS = {
    "fact_basket_state": {"state", "basket_id"},
    "fact_spending_state": {"state", "group_code"},
    "fact_state_year": {"state"},
    "fact_district_year": {"district_key"},
    "mart_burden": {"state", "basket_id", "percentile"},
    "mart_counterfactual": {"state", "basket_id", "percentile"},
    "mart_decomposition": {"basket_id", "percentile"},
    "mart_budget_gap": {"state", "household_type"},
}

COLUMN_FORMATS = {
    ("fact_district_year", "income_median"): "#,0",
    ("fact_district_year", "exp_share_mean_pct"): "0.0",
    ("fact_district_year", "gini"): "0.000",
    ("fact_district_year", "poverty_rate"): "0.0",
}

SORT_BY = {
    ("dim_basket", "basket_name"): "basket_order",
    ("dim_income_position", "label"): "position_order",
    ("dim_household_type", "household_type"): "household_order",
}


def tag(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def q(name):
    return f"'{name}'" if any(ch in name for ch in " -()/%·÷") else name


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def s(text):
    return lit("'" + str(text).replace("'", "''") + "'")


def color(hexv):
    return {"solid": {"color": lit(f"'{hexv}'")}}


def measure_ref(prop, entity=MT):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def col_ref(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(entity, prop, display=None, measure=False, active=None):
    p = {"field": measure_ref(prop, entity) if measure else col_ref(entity, prop),
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    if active:
        p["active"] = True
    return p


def M(prop, display=None):
    return proj(MT, prop, display, measure=True)


def C(entity, prop, display=None, active=None):
    return proj(entity, prop, display, active=active)


def padding(t, b, l, r):
    return [{"properties": {"top": lit(f"{t}D"), "bottom": lit(f"{b}D"), "left": lit(f"{l}D"), "right": lit(f"{r}D")}}]


def map_type(arrow_type):
    t = arrow_type.lower()
    if t.startswith("int"):
        return "int64", "Int64.Type", False
    if t in ("double", "float"):
        return "double", "type number", False
    if t == "bool":
        return "boolean", "type logical", False
    if t.startswith("date"):
        return "dateTime", "type date", True
    return "string", "type text", False


def read_schema(table):
    schema = pq.read_schema(PROCESSED_DIR / f"{table}.parquet")
    return [(f.name, *map_type(str(f.type))) for f in schema]


def tmdl_parquet_table(name):
    cols = read_schema(name)
    out = [f"table {name}", f"\tlineageTag: {tag(name)}", ""]
    hidden = FACT_KEY_COLS.get(name, set())

    for c, tmdl_type, _, is_date in cols:
        out += [f"\tcolumn {q(c)}", f"\t\tdataType: {tmdl_type}"]
        if c in hidden:
            out.append("\t\tisHidden")
        if is_date:
            out.append("\t\tformatString: mmm yyyy")
        elif (name, c) in COLUMN_FORMATS:
            out.append(f"\t\tformatString: {COLUMN_FORMATS[(name, c)]}")
        out += [f"\t\tlineageTag: {tag(name, c)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}"]
        if (name, c) in SORT_BY:
            out.append(f"\t\tsortByColumn: {SORT_BY[(name, c)]}")
        if is_date:
            out += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
        out.append("")

    selected = ", ".join(f'"{c[0]}"' for c in cols)
    typed = ",\n".join(f'\t\t\t\t        {{"{c[0]}", {c[2]}}}' for c in cols)
    out += [
        f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
        f'\t\t\t\t    Source = Parquet.Document(File.Contents(ProcessedFolder & "\\{name}.parquet")),',
        f'\t\t\t\t    #"Selected" = Table.SelectColumns(Source, {{{selected}}}),',
        '\t\t\t\t    #"Typed" = Table.TransformColumnTypes(#"Selected", {',
        typed, "\t\t\t\t    })", "\t\t\t\tin", '\t\t\t\t    #"Typed"', "",
    ]
    return "\n".join(out)


def measure_lines(name, expr, fmt=None, folder=None):
    lines = expr.strip().splitlines()
    if len(lines) == 1:
        out = [f"\tmeasure {q(name)} = {lines[0]}"]
    else:
        out = [f"\tmeasure {q(name)} ="] + [f"\t\t\t{ln}" for ln in lines]
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if folder:
        out.append(f"\t\tdisplayFolder: {folder}")
    out += [f"\t\tlineageTag: {tag(MT, 'm', name)}", ""]
    return out


# Every measure resolves its own selection, so a cleared slicer falls back to a stated
# default and can never add up several baskets or income positions.
SELECT = """VAR q = SELECTEDVALUE ( Purchases[n], 4 )
VAR b = SELECTEDVALUE ( dim_basket[basket_id], "staples_plus_rice" )
VAR p = SELECTEDVALUE ( dim_income_position[percentile], 10 )
"""

INCOME = """CALCULATE (
    AVERAGE ( mart_burden[income_2024] ),
    REMOVEFILTERS ( dim_basket ),
    REMOVEFILTERS ( dim_income_position ),
    mart_burden[basket_id] = b,
    mart_burden[percentile] = p
)"""


def basket_value(column):
    return f"""CALCULATE (
    AVERAGE ( fact_basket_state[{column}] ),
    REMOVEFILTERS ( dim_basket ),
    fact_basket_state[basket_id] = b
)"""


def burden_from(column):
    return f"""{SELECT}VAR cost = {basket_value(column)}
VAR inc = {INCOME}
RETURN
    IF ( NOT ISBLANK ( cost ) && NOT ISBLANK ( inc ), DIVIDE ( q * cost, inc ) * 100 )"""


def decomposition(column):
    return f"""{SELECT}RETURN
    CALCULATE (
        AVERAGE ( mart_decomposition[{column}] ),
        REMOVEFILTERS ( dim_basket ),
        REMOVEFILTERS ( dim_income_position ),
        mart_decomposition[basket_id] = b,
        mart_decomposition[percentile] = p
    )"""


def counterfactual(column):
    return f"""{SELECT}VAR stored =
    CALCULATE (
        AVERAGE ( mart_counterfactual[{column}] ),
        REMOVEFILTERS ( dim_basket ),
        REMOVEFILTERS ( dim_income_position ),
        mart_counterfactual[basket_id] = b,
        mart_counterfactual[percentile] = p
    )
RETURN
    IF ( NOT ISBLANK ( stored ), stored * q / 4 )"""


def household(column):
    return f"""VAR h = SELECTEDVALUE ( dim_household_type[household_type], "Married (2 Children)" )
RETURN
    CALCULATE (
        AVERAGE ( mart_budget_gap[{column}] ),
        REMOVEFILTERS ( dim_household_type ),
        mart_budget_gap[household_type] = h
    )"""


def spending(code):
    return f"""CALCULATE (
    AVERAGE ( fact_spending_state[share_pct] ),
    REMOVEFILTERS ( dim_spending_group ),
    fact_spending_state[group_code] = "{code}"
)"""


STATES = """VAR States =
    FILTER (
        ADDCOLUMNS ( VALUES ( dim_state[state] ), "@Burden", [Burden %] ),
        NOT ISBLANK ( [@Burden] )
    )
"""

MEASURES = [
    ("Burden %", burden_from("basket_cost_2024"), PCT, "Burden"),
    ("Burden CI Low %", burden_from("ci_lower"), PCT, "Burden"),
    ("Burden CI High %", burden_from("ci_upper"), PCT, "Burden"),
    ("Basket Cost 2024 (RM)", f"{SELECT}RETURN\n{basket_value('basket_cost_2024')}", RM2, "Base"),
    ("Income at Position (RM)", f"{SELECT}RETURN\n{INCOME}", RM0, "Base"),
    ("Monthly Basket Spend (RM)", "SELECTEDVALUE ( Purchases[n], 4 ) * [Basket Cost 2024 (RM)]", RM2, "Base"),
    ("Highest Burden State", f"{STATES}RETURN\n    MAXX ( TOPN ( 1, States, [@Burden], DESC ), dim_state[state] )", None, "Ranking"),
    ("Highest Burden Value", f"{STATES}RETURN\n    MAXX ( States, [@Burden] )", PCT, "Ranking"),
    ("Lowest Burden State", f"{STATES}RETURN\n    MINX ( TOPN ( 1, States, [@Burden], ASC ), dim_state[state] )", None, "Ranking"),
    ("Lowest Burden Value", f"{STATES}RETURN\n    MINX ( States, [@Burden] )", PCT, "Ranking"),
    ("Burden Gap (x)", "DIVIDE ( [Highest Burden Value], [Lowest Burden Value] )", TIMES, "Ranking"),
    ("Price Share of Gap %", decomposition("share_due_to_price_pct"), SIGNED, "Decomposition"),
    ("Income Share of Gap %", decomposition("share_due_to_income_pct"), PCT, "Decomposition"),
    ("Burden with Typical Price %", counterfactual("typical_price_burden_pct"), PCT, "Counterfactual"),
    ("Burden with Malaysia Income %", counterfactual("mys_income_burden_pct"), PCT, "Counterfactual"),
    ("Pressure Signals Label", """VAR sig = SELECTEDVALUE ( mart_pressure[pressure_signals] )
VAR avail = SELECTEDVALUE ( mart_pressure[signals_available] )
RETURN
    IF ( NOT ISBLANK ( sig ), sig & " of " & avail )""", None, "Pressure"),
    ("Selection Label", f"""{SELECT}VAR basket =
    SWITCH (
        b,
        "core", "Core 7",
        "staples_16", "Staples 16",
        "Staples + rice"
    )
RETURN
    basket & " · P" & p & " · " & q & " purchases a month\"""", None, "Titles"),
    ("Budget % Households Below", household("pct_households_below"), "0\\%", "Budgets"),
    ("Budget RM", household("budget_rm"), RM0, "Budgets"),
    ("Budget as % of Median", household("budget_pct_of_median"), PCT, "Budgets"),
    ("Budget City", "SELECTEDVALUE ( mart_budget_gap[city] )", None, "Budgets"),
    ("Selected Household Label", 'SELECTEDVALUE ( dim_household_type[household_type], "Married (2 Children)" )', None, "Titles"),
    ("P10 ÷ Average PLI", "AVERAGE ( mart_pli[p10_multiple_of_pli] )", TIMES, "Budgets"),
    ("Real Income Growth %", "AVERAGE ( mart_real_income[real_median_growth_pct] )", SIGNED, "Growth"),
    ("Real Wage Growth %", "AVERAGE ( mart_real_wages[real_wage_growth_pct] )", SIGNED, "Growth"),
    ("Food Share %", spending("01"), PCT, "Spending"),
    ("Eating Out Share %", spending("11"), PCT, "Spending"),
    ("Housing Share %", spending("04"), PCT, "Spending"),
    ("Transport Share %", spending("07"), PCT, "Spending"),
    ("Spending Share of Income %", "CALCULATE ( AVERAGE ( fact_state_year[exp_share_mean_pct] ), fact_state_year[year] = 2024 )", PCT, "Spending"),
    ("Poverty Rate %", "CALCULATE ( AVERAGE ( fact_state_year[poverty_rate] ), fact_state_year[year] = 2024 )", PCT, "Base"),
    ("Thin Coverage Note", """IF (
    HASONEVALUE ( dim_state[state] ) && SELECTEDVALUE ( dim_state[thin_coverage_flag] ),
    "Thin shop coverage"
)""", None, "Formatting"),
    ("Title Burden Chart", '"Basket as a share of income · " & [Selection Label]', None, "Titles"),
    ("Title Income Bar", '"Income · " & SELECTEDVALUE ( dim_income_position[label], "P10: lower-income household" )', None, "Titles"),
    ("Title Basket Bar", '"Basket cost, 2024"', None, "Titles"),
    ("Title Counterfactual", '"Burden if prices or incomes were swapped · " & [Selection Label]', None, "Titles"),
    ("Title Budget Gap Bar", '"Households earning under the budget · " & [Selected Household Label]', None, "Titles"),
    ("Title Budget Gap Table", '"Budget and poverty benchmarks · " & [Selected Household Label]', None, "Titles"),
    ("Title District Table", '"Districts, 2024 · " & SELECTEDVALUE ( dim_state[state], "all covered states" )', None, "Titles"),
    # Stored values are already percentage points, so they are formatted as plain numbers
    ("Card Highest Burden", '[Highest Burden State] & " · " & FORMAT ( [Highest Burden Value], "0.0" ) & "%"', None, "KPI"),
    ("Card Lowest Burden", '[Lowest Burden State] & " · " & FORMAT ( [Lowest Burden Value], "0.0" ) & "%"', None, "KPI"),
    ("Card Burden Gap", 'FORMAT ( [Burden Gap (x)], "0.0" ) & " times"', None, "KPI"),
    ("Card Income Share", 'FORMAT ( [Income Share of Gap %], "0.0" ) & "%"', None, "KPI"),
    ("Card Price Share", 'FORMAT ( [Price Share of Gap %], "+0.0;-0.0;0.0" ) & "%"', None, "KPI"),
    ("KPI Selection", "[Selection Label]", None, "Labels"),
    ("KPI Gap Label", '"Highest burden divided by lowest"', None, "Labels"),
    ("KPI Income Share Label", '"Of the gap between states, from income"', None, "Labels"),
    ("KPI Price Share Label", '"Of the gap between states, from prices"', None, "Labels"),
]


def tmdl_measures_table():
    out = [f"table {MT}", f"\tlineageTag: {tag(MT)}", ""]
    for m in MEASURES:
        out += measure_lines(*m)
    out += [
        "\tcolumn Value", "\t\tdataType: int64", "\t\tisHidden", "\t\tformatString: 0",
        f"\t\tlineageTag: {tag(MT, 'Value')}", "\t\tsummarizeBy: none", "\t\tisNameInferred",
        "\t\tsourceColumn: [Value]", "",
        f"\tpartition {MT} = calculated", "\t\tmode: import", "\t\tsource = {0}", "",
    ]
    return "\n".join(out)


def tmdl_purchases_table():
    return "\n".join([
        "table Purchases", f"\tlineageTag: {tag('Purchases')}", "",
        "\tcolumn n", "\t\tdataType: int64", "\t\tformatString: 0",
        f"\t\tlineageTag: {tag('Purchases', 'n')}", "\t\tsummarizeBy: none", "\t\tisNameInferred",
        "\t\tsourceColumn: [n]", "",
        "\tpartition Purchases = calculated", "\t\tmode: import",
        '\t\tsource = SELECTCOLUMNS ( GENERATESERIES ( 2, 6, 1 ), "n", [Value] )', "",
    ])


def tmdl_relationships():
    links = [(t, "state", "dim_state") for t in (
        "mart_burden", "mart_counterfactual", "mart_budget_gap", "mart_pli", "mart_pressure",
        "mart_real_income", "mart_real_wages", "fact_state_year", "fact_district_year",
        "fact_spending_state", "fact_basket_state")]
    links += [(t, "basket_id", "dim_basket") for t in
              ("mart_burden", "mart_counterfactual", "mart_decomposition", "fact_basket_state")]
    links += [(t, "percentile", "dim_income_position") for t in
              ("mart_burden", "mart_counterfactual", "mart_decomposition")]
    links += [("mart_budget_gap", "household_type", "dim_household_type"),
              ("fact_spending_state", "group_code", "dim_spending_group")]
    out = []
    for table, column, dim in links:
        out += [f"relationship {tag('rel', table, column)}",
                f"\tfromColumn: {table}.{column}", f"\ttoColumn: {dim}.{column}", ""]
    return "\n".join(out)


def platform_json(kind):
    return json.dumps({
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind, "displayName": NAME},
        "config": {"version": "2.0", "logicalId": tag("platform", kind)}}, indent=2)


def model_files():
    all_tables = TABLES + ["Purchases", MT]
    escaped_dir = str(PROCESSED_DIR.resolve()).replace("\\", "\\\\")
    files = {
        ".platform": platform_json("SemanticModel"),
        "definition.pbism": json.dumps({
            "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2", "settings": {}}, indent=2),
        "definition/database.tmdl": "database\n\tcompatibilityLevel: 1567\n",
        "definition/cultures/en-US.tmdl": (
            'cultureInfo en-US\n\n\tlinguisticMetadata =\n\t\t\t{\n\t\t\t  "Version": "2.0.0",\n'
            '\t\t\t  "Language": "en-US"\n\t\t\t}\n\t\tcontentType: json\n'),
        "definition/model.tmdl": "\n".join([
            "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
            "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects",
            "\t\treturnErrorValuesAsNull", "",
            "annotation __PBI_TimeIntelligenceEnabled = 0", "",
            f"annotation PBI_QueryOrder = {json.dumps(['ProcessedFolder'] + TABLES)}", "",
            'annotation PBI_ProTooling = ["DevMode"]', "",
            *[f"ref table {t}" for t in all_tables], "", "ref cultureInfo en-US", ""]),
        "definition/expressions.tmdl": (
            f'expression ProcessedFolder = "{escaped_dir}" meta [IsParameterQuery=true, Type="Text", '
            f'IsParameterQueryRequired=true]\n\tlineageTag: {tag("ProcessedFolder")}\n\n'
            "\tannotation PBI_ResultType = Text\n"),
        "definition/relationships.tmdl": tmdl_relationships(),
        "definition/tables/Purchases.tmdl": tmdl_purchases_table(),
        f"definition/tables/{MT}.tmdl": tmdl_measures_table(),
    }
    for name in TABLES:
        files[f"definition/tables/{name}.tmdl"] = tmdl_parquet_table(name)
    return files


class Page:
    def __init__(self, name, display):
        self.name, self.display, self.visuals, self.z = name, display, {}, 1000

    def add(self, name, pos, visual, title=None, subtitle=None, alt=None, background=True, pad=None):
        x, y, w, h = pos
        self.z += 1000
        vco = {
            "title": [{"properties": {"show": lit("true" if title else "false")}}],
            "background": [{"properties": {"show": lit("true" if background else "false")}}],
        }
        if title:
            vco["title"][0]["properties"]["text"] = title if isinstance(title, dict) else s(title)
        if subtitle:
            vco["subTitle"] = [{"properties": {"show": lit("true"), "text": s(subtitle)}}]
        if alt:
            vco["general"] = [{"properties": {"altText": s(alt)}}]
        if pad:
            vco["padding"] = padding(*pad)
        self.visuals[name] = {
            "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.3.0/schema.json",
            "name": name, "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z},
            "visual": {**visual, "visualContainerObjects": vco, "drillFilterOtherVisuals": True},
        }

    def text(self, name, pos, paragraphs, background=False, alt=None):
        runs = [{"textRuns": [{"value": v, "textStyle": {"fontFamily": f, "fontSize": sz, "color": c}}]}
                for v, f, sz, c in paragraphs]
        self.add(name, pos, {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": runs}}]}},
                 background=background, pad=(0, 0, 0, 0) if not background else (8, 8, 12, 12), alt=alt)

    def header(self, pos, title, subtitle):
        self.text("header", pos, [(title, "Segoe UI Semibold", "16pt", INK), (subtitle, "Segoe UI", "9pt", MUTED)],
                  alt=f"{title} {subtitle}")

    def kpi(self, key, pos, value_measure, label_measure, title, alt):
        x, y, w, h = pos
        self.add(f"kpi_{key}_tile", pos, {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": []}}]}},
                 background=True, pad=(0, 0, 0, 0), alt=f"Background for {title}")
        self.add(f"kpi_{key}_value", (x, y, w, 56),
                 {"visualType": "card", "query": {"queryState": {"Values": {"projections": [M(value_measure)]}}},
                  "objects": {"labels": [{"properties": {"fontSize": lit("18D")}}]}},
                 title=title, alt=alt, background=False, pad=(6, 0, 16, 16))
        props = self.visuals[f"kpi_{key}_value"]["visual"]["visualContainerObjects"]["title"][0]["properties"]
        props.update({"fontSize": lit("10D"), "fontColor": color(MUTED), "alignment": s("left")})
        self.add(f"kpi_{key}_label", (x, y + 56, w, h - 56),
                 {"visualType": "card", "query": {"queryState": {"Values": {"projections": [M(label_measure)]}}},
                  "objects": {"labels": [{"properties": {"fontSize": lit("9D"), "color": color(MUTED)}}]}},
                 background=False, pad=(0, 0, 16, 16), alt=f"Note for {title}")

    def slicer(self, name, pos, entity, column, display, alt=None, single=True, default=None):
        objects = {
            "data": [{"properties": {"mode": s("Dropdown")}}],
            "header": [{"properties": {"show": lit("true"), "text": s(display)}}],
        }
        if single:
            objects["selection"] = [{"properties": {"singleSelect": lit("true")}}]
        if default is not None:
            objects["general"] = [{"properties": {"filter": {"filter": {
                "Version": 2, "From": [{"Name": "d", "Entity": entity, "Type": 0}],
                "Where": [{"Condition": {"In": {
                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": column}}],
                    "Values": [[{"Literal": {"Value": default}}]]}}}]}}}}]
        self.add(name, pos, {"visualType": "slicer",
                             "query": {"queryState": {"Values": {"projections": [C(entity, column, display, True)]}}},
                             "objects": objects}, alt=alt, pad=(4, 4, 12, 12))

    def bar(self, name, pos, category, measures, title, subtitle=None, alt=None, sort=None, tooltips=None):
        state = {
            "Category": {"projections": [C(category[0], category[1], active=True)]},
            "Y": {"projections": [M(*m) for m in measures]},
        }
        if tooltips:
            state["Tooltips"] = {"projections": [M(t) for t in tooltips]}
        objects = {
            "dataPoint": [{"properties": {"fill": color(BLUE)}}] if len(measures) == 1 else [
                {"properties": {"fill": color(c)}, "selector": {"metadata": f"{MT}.{m[0]}"}}
                for m, c in zip(measures, SERIES)
            ],
            "categoryAxis": [{"properties": {"maxMarginFactor": lit("40L")}}],
            "labels": [{"properties": {"show": lit("true"), "labelPosition": s("OutsideEnd")}}],
        }
        if len(measures) > 1:
            objects["legend"] = [{"properties": {"show": lit("true"), "position": s("Top")}}]
        v = {"visualType": "clusteredBarChart", "query": {"queryState": state}, "objects": objects}
        if sort:
            v["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}]}
        self.add(name, pos, v, title=title, subtitle=subtitle, alt=alt, pad=(8, 8, 16, 16))

    def table(self, name, pos, projections, title, subtitle=None, alt=None, sort=None, widths=None):
        objects = {
            "total": [{"properties": {"totals": lit("false")}}],
            "columnHeaders": [{"properties": {"wordWrap": lit("true")}}],
        }
        if widths:
            objects["columnWidth"] = [
                {"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": pr["queryRef"]}}
                for pr, w in zip(projections, widths)
            ]
        v = {"visualType": "tableEx", "query": {"queryState": {"Values": {"projections": projections}}}, "objects": objects}
        if sort:
            v["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}]}
        self.add(name, pos, v, title=title, subtitle=subtitle, alt=alt, pad=(8, 8, 16, 16))

    def footnote(self, pos, text):
        self.text("footnote", pos, [(text, "Segoe UI", "8.5pt", MUTED)], alt=f"Footnote: {text}")

    def files(self):
        bg = {"color": color("#F4F6F9"), "transparency": lit("0D")}
        out = {f"definition/pages/{self.name}/page.json": {
            "$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
            "name": self.name, "displayName": self.display, "displayOption": "FitToPage", "height": 720, "width": 1280,
            "objects": {"background": [{"properties": bg}], "outspace": [{"properties": bg}]}}}
        for name, visual in self.visuals.items():
            out[f"definition/pages/{self.name}/visuals/{name}/visual.json"] = visual
        return out


def title_measure(name):
    return {"expr": measure_ref(name)}


def page_pressure():
    p = Page("pressure", "Who is under pressure?")
    p.header((16, 16, 1248, 48), "Who is under pressure?",
             "What a basket of essentials takes from household income, by state. KPDN PriceCatcher and DOSM HIES 2024.")
    p.slicer("slicer_basket", (16, 72, 304, 56), "dim_basket", "basket_name", "Basket", "Choose a basket.", default=BASKET)
    p.slicer("slicer_position", (328, 72, 304, 56), "dim_income_position", "label", "Income position", "Choose an income position.", default=POSITION)
    p.slicer("slicer_purchases", (640, 72, 304, 56), "Purchases", "n", "Purchases per month", "Choose purchases per month.", default="4L")
    p.slicer("slicer_region", (952, 72, 312, 56), "dim_state", "region", "Region", "Choose a region.", single=False)

    p.kpi("highest", (16, 136, 304, 88), "Card Highest Burden", "KPI Selection", "Highest burden", "State with the highest burden.")
    p.kpi("lowest", (328, 136, 304, 88), "Card Lowest Burden", "KPI Selection", "Lowest burden", "State with the lowest burden.")
    p.kpi("gap", (640, 136, 304, 88), "Card Burden Gap", "KPI Gap Label", "Gap between them", "Highest burden divided by lowest.")
    p.kpi("income", (952, 136, 312, 88), "Card Income Share", "KPI Income Share Label", "What income explains",
          "Share of the gap between states that comes from income.")

    p.bar("bar_burden", (16, 232, 616, 440), ("dim_state", "state"), [("Burden %", "Burden")],
          title_measure("Title Burden Chart"), "Hover a bar for the cost, the income and the 95% interval.",
          "Bar chart of basket burden by state, highest first.",
          sort=(measure_ref("Burden %"), "Descending"),
          tooltips=["Basket Cost 2024 (RM)", "Income at Position (RM)", "Burden CI Low %", "Burden CI High %"])

    p.table("table_pressure", (640, 232, 624, 440),
            [C("mart_pressure", "state", "State"),
             C("mart_pressure", "rank_p10_burden", "P10 burden"),
             C("mart_pressure", "rank_exp_share", "Spending share"),
             C("mart_pressure", "rank_budget_gap", "Under budget"),
             C("mart_pressure", "rank_poverty", "Poverty"),
             C("mart_pressure", "rank_real_income_growth", "Income growth"),
             M("Pressure Signals Label", "Signals")],
            "Pressure across five measures",
            "Rank 1 is most pressure. A signal is a top-four rank. No weights. Perlis and W.P. Labuan have four measures.",
            "Table of pressure ranks and signals by state.",
            sort=(measure_ref("Pressure Signals Label"), "Descending"),
            widths=[128, 72, 72, 72, 72, 72, 72])

    p.footnote((16, 680, 1248, 24), "Burden shows relative pressure. Purchases per month is an assumption, not a measurement. "
                                    "Above 100% means prices slightly offset the gap.")
    return p


def page_drivers():
    p = Page("drivers", "What drives it?")
    p.header((16, 16, 616, 56), "What drives it?", "Prices against incomes, swapped one at a time, and where the money goes.")
    p.slicer("slicer_basket", (640, 16, 304, 56), "dim_basket", "basket_name", "Basket", "Choose a basket.", default=BASKET)
    p.slicer("slicer_position", (952, 16, 312, 56), "dim_income_position", "label", "Income position", "Choose an income position.", default=POSITION)

    p.bar("bar_income", (16, 80, 304, 400), ("dim_state", "state"), [("Income at Position (RM)", "Income")],
          title_measure("Title Income Bar"), "Lowest income first.", "Bar chart of income by state, lowest first.",
          sort=(measure_ref("Income at Position (RM)"), "Ascending"))
    p.bar("bar_cost", (328, 80, 304, 400), ("dim_state", "state"), [("Basket Cost 2024 (RM)", "Cost")],
          title_measure("Title Basket Bar"), "Same state order as the income chart.",
          "Bar chart of basket cost by state, in the order of the income chart.",
          sort=(measure_ref("Income at Position (RM)"), "Ascending"), tooltips=["Income at Position (RM)"])

    p.kpi("price", (640, 80, 304, 80), "Card Price Share", "KPI Price Share Label", "From prices",
          "Share of the gap between states from prices.")
    p.kpi("income", (952, 80, 312, 80), "Card Income Share", "KPI Income Share Label", "From income",
          "Share of the gap between states from income.")

    p.bar("bar_counterfactual", (640, 168, 624, 312), ("dim_state", "state"),
          [("Burden %", "Actual"), ("Burden with Typical Price %", "With a typical price"),
           ("Burden with Malaysia Income %", "With Malaysia's income")],
          title_measure("Title Counterfactual"), "A typical price is the unweighted average across states.",
          "Bar chart of actual burden against burden with a typical price and with Malaysia's income.",
          sort=(measure_ref("Burden %"), "Descending"))

    p.table("table_spending", (16, 488, 1248, 184),
            [C("dim_state", "state", "State"),
             M("Food Share %", "Food at home"), M("Eating Out Share %", "Eating out"),
             M("Housing Share %", "Housing and utilities"), M("Transport Share %", "Transport"),
             M("Spending Share of Income %", "Spending as a share of income")],
            "Where the average household's money goes, 2024",
            "First four columns are shares of household spending. DOSM household expenditure, Table 4.2.",
            "Table of spending shares by state.",
            sort=(measure_ref("Spending Share of Income %"), "Descending"),
            widths=[180, 190, 190, 190, 190, 220])

    p.footnote((16, 680, 1248, 24), "A share below zero means that factor offsets the gap. Spending share is average household, mean over mean.")
    return p


def page_budgets():
    p = Page("budgets", "Can households meet a reference budget?")
    p.header((16, 16, 840, 56), "Can households meet a reference budget?",
             "Household incomes against Belanjawanku 2024/2025 budgets and the poverty line (PGK).")
    p.slicer("slicer_household", (864, 16, 400, 56), "dim_household_type", "household_type", "Household type", "Choose a household type.", default=HOUSEHOLD)

    p.bar("bar_budget_gap", (16, 80, 528, 584), ("dim_state", "state"), [("Budget % Households Below", "Under budget")],
          title_measure("Title Budget Gap Bar"), "Highest share first.",
          "Bar chart of the share of households earning under the budget, by state.",
          sort=(measure_ref("Budget % Households Below"), "Descending"))

    p.table("table_budget_detail", (552, 80, 712, 584),
            [C("dim_state", "state", "State"), M("Budget City", "City"), M("Budget RM", "Budget"),
             M("Budget as % of Median", "Budget against median income"), M("P10 ÷ Average PLI", "P10 against average PGK"),
             M("Poverty Rate %", "Poverty rate")],
            title_measure("Title Budget Gap Table"), "Belanjawanku 2024/2025 and DOSM 2024.",
            "Table of budgets, poverty line comparison and poverty rate by state.",
            sort=(measure_ref("Budget as % of Median"), "Descending"),
            widths=[128, 120, 96, 120, 112, 96])

    p.footnote((16, 672, 1248, 32),
               "Share of all households in the state earning under this budget, not the share of households of this type.  "
               "Perlis and W.P. Labuan have no Belanjawanku city. PGK is set per household, so the state average is not a strict cut-off.")
    return p


def page_growth():
    p = Page("growth", "What has changed, and where within states?")
    p.header((16, 16, 960, 56), "What has changed, and where within states?",
             "Real income and wages against state prices, then the districts within each state.")
    p.slicer("slicer_state", (984, 16, 280, 56), "dim_state", "state", "State", "Choose a state.", single=False)

    p.bar("bar_real_income", (16, 80, 616, 384), ("dim_state", "state"), [("Real Income Growth %", "Real income growth")],
          "Real median household income, 2022 to 2024", "DOSM HIES, adjusted by state CPI.",
          "Bar chart of real median income growth by state.",
          sort=(measure_ref("Real Income Growth %"), "Ascending"))
    p.bar("bar_real_wages", (640, 80, 624, 384), ("dim_state", "state"), [("Real Wage Growth %", "Real wage growth")],
          "Real formal median wages, Jul 2022-Jun 2023 to Jul 2025-Jun 2026", "Twelve-month medians, adjusted by state CPI.",
          "Bar chart of real formal wage growth by state.",
          sort=(measure_ref("Real Wage Growth %"), "Ascending"))

    p.table("table_districts", (16, 472, 1248, 192),
            [C("fact_district_year", "district", "District"), C("fact_district_year", "state", "State"),
             C("fact_district_year", "income_median", "Median income (RM)"),
             C("fact_district_year", "exp_share_mean_pct", "Spending as % of income"),
             C("fact_district_year", "gini", "Gini"), C("fact_district_year", "poverty_rate", "Poverty rate (%)")],
            title_measure("Title District Table"), "Highest poverty rate first.",
            "Table of districts with income, spending share, Gini and poverty rate.",
            sort=(col_ref("fact_district_year", "poverty_rate"), "Descending"),
            widths=[220, 160, 160, 180, 120, 160])

    p.footnote((16, 672, 1248, 32),
               "Formal-sector employees only.  District data covers 12 states; DOSM's 2024 district file has no rows "
               "for Perlis, W.P. Kuala Lumpur, W.P. Labuan or W.P. Putrajaya. No district prices: shop coverage is too thin.")
    return p


def report_theme():
    axis = {"labelColor": {"solid": {"color": MUTED}}, "fontSize": 9, "fontFamily": "Segoe UI", "showAxisTitle": False}
    return {
        "name": NAME, "dataColors": SERIES, "background": "#FFFFFF", "foreground": INK, "tableAccent": BLUE,
        "good": "#16A34A", "neutral": MUTED, "bad": "#DC2626",
        "textClasses": {
            "callout": {"fontSize": 26, "fontFace": "Segoe UI Semibold", "color": INK},
            "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
            "header": {"fontSize": 10, "fontFace": "Segoe UI Semibold", "color": INK},
            "label": {"fontSize": 9, "fontFace": "Segoe UI", "color": MUTED},
        },
        "visualStyles": {
            "page": {"*": {"background": [{"color": {"solid": {"color": "#F4F6F9"}}, "transparency": 0}],
                           "outspace": [{"color": {"solid": {"color": "#F4F6F9"}}, "transparency": 0}]}},
            "*": {"*": {"background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
                        "border": [{"show": False, "radius": 6}], "dropShadow": [{"show": False}],
                        "padding": [{"top": 8, "bottom": 8, "left": 12, "right": 12}],
                        "title": [{"show": True, "fontColor": {"solid": {"color": INK}}, "fontSize": 11,
                                   "fontFamily": "Segoe UI Semibold", "alignment": "left"}],
                        "subTitle": [{"fontColor": {"solid": {"color": MUTED}}, "fontSize": 8.5}]}},
            "card": {"*": {"labels": [{"color": {"solid": {"color": INK}}, "fontSize": 24, "fontFamily": "Segoe UI Semibold"}],
                           "categoryLabels": [{"show": False}]}},
            "clusteredBarChart": {"*": {"categoryAxis": [axis], "valueAxis": [{**axis, "show": False}],
                                        "labels": [{"show": True, "color": {"solid": {"color": INK}}, "fontSize": 8.5}]}},
            "tableEx": {"*": {"grid": [{"gridHorizontal": True, "gridHorizontalColor": {"solid": {"color": "#E2E8F0"}},
                                        "gridVertical": False, "rowPadding": 2}],
                              "columnHeaders": [{"fontColor": {"solid": {"color": MUTED}}, "fontSize": 9,
                                                 "backColor": {"solid": {"color": "#FFFFFF"}}}],
                              "values": [{"fontSize": 9, "fontColorPrimary": {"solid": {"color": INK}},
                                          "backColorPrimary": {"solid": {"color": "#FFFFFF"}},
                                          "backColorSecondary": {"solid": {"color": "#FFFFFF"}}}]}},
            "slicer": {"*": {"header": [{"fontColor": {"solid": {"color": MUTED}}, "fontSize": 9}],
                             "items": [{"fontColor": {"solid": {"color": INK}}, "fontSize": 9.5}]}},
        },
    }


def report_files():
    pages = [page_pressure(), page_drivers(), page_budgets(), page_growth()]
    files = {
        ".platform": platform_json("Report"),
        "definition.pbir": {
            "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
        },
        "definition/version.json": {
            "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0",
        },
        "definition/report.json": {
            "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
            "themeCollection": {"customTheme": {"name": f"{NAME}.json", "reportVersionAtImport": {
                "visual": "2.3.0", "report": "3.0.0", "page": "2.0.0"}, "type": "RegisteredResources"}},
            "objects": {"outspacePane": [{"properties": {"expanded": lit("false")}}]},
            "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources", "items": [
                {"name": f"{NAME}.json", "path": f"{NAME}.json", "type": "CustomTheme"}]}],
            "settings": {"useEnhancedTooltips": True},
        },
        "definition/pages/pages.json": {
            "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": [p.name for p in pages], "activePageName": pages[0].name,
        },
        f"StaticResources/RegisteredResources/{NAME}.json": report_theme(),
    }
    for p in pages:
        files.update(p.files())
    return files


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False)
    text = text.replace("\r\n", "\n")
    path.write_bytes((text if text.endswith("\n") else text + "\n").encode("utf-8"))


def main():
    report_dir = PBI / f"{NAME}.Report"
    model_dir = PBI / f"{NAME}.SemanticModel"
    pbip_file = PBI / f"{NAME}.pbip"

    for folder in (report_dir, model_dir):
        if folder.exists():
            shutil.rmtree(folder)
    pbip_file.unlink(missing_ok=True)

    for rel, content in model_files().items():
        write_file(model_dir / rel, content)
    for rel, content in report_files().items():
        write_file(report_dir / rel, content)
    write_file(pbip_file, {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    print(f"[OK] Generated {pbip_file}")


if __name__ == "__main__":
    main()
