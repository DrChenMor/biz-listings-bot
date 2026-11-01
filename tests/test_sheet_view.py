import re

from bizbot import sheet_view as view


def kinds(text):
    """The groups a listing falls in, the way the sheet's formula decides: lower case, broad headings out, then match."""
    text = re.sub(view.TYPE_NOISE, "", text.lower())
    return [name for name, pattern in view.BUSINESS_TYPES[1:] if re.search(pattern, text)]


def test_business_types_go_by_what_the_business_really_is():
    assert kinds("Beauty and Health Hair Salon") == ["Beauty and hair"]
    assert kinds("Beauty and Health Gym") == ["Fitness and sport"]
    assert kinds("Beauty and Health Medical") == ["Health and medical"]
    assert kinds("Hairdresser Hairdresser, Beauty, Health & Fitness") == ["Beauty and hair"]
    assert kinds("Health, Beauty & Fitness > Health & Medical > Pharmacy Business") == ["Health and medical"]
    assert kinds("Personal Services > Pet products & services > Dog Grooming Business") == ["Pets and animals"]
    assert kinds("Automotive Transport") == ["Automotive and transport"]  # not sport
    assert kinds("Manufacturing Building and Construction") == ["Trades and construction"]
    assert kinds("Cleaning Services Cleaning Services, Professional Services") == ["Cleaning and home services"]
    assert "Franchises" in kinds("Franchise Franchise Business Opportunities, Gym")


def test_styles_only_name_columns_that_exist():
    for spec in view.DATA_TABS + view.LOG_TABS:
        named = set(spec["widths"]) | set(spec.get("hide", [])) | set(spec.get("money", [])) | {spec.get("new_since", "Key")}
        assert named - {"Key"} <= set(spec["table"].headers)


def test_search_tab_formulas_read_from_row_1_so_new_rows_are_never_missed():
    data = view._find_data_formula()
    assert "'Listings'!T1:T" in data and "'CRE listings'!T1:T" in data and "'SEEK listings'!P1:P" in data
    for formula in (data, view._business_results(), view._health_results()):
        assert not re.search(r"![A-Z]+2:", formula)
