"""The demo data for the SkiLifts table.

The 19 items are the rows of the spec's sample tables, copied verbatim with the
table's own attribute names. Four are profiles, twelve are lift days, and three
are resort days under the ``Resort Data`` partition.
"""

ITEMS: list[dict] = [
    # Profiles: one item per lift, sort key is the literal ``Static Data``.
    {
        "Lift": "Lift 3",
        "Metadata": "Static Data",
        "ExperiencedRidersOnly": False,
        "VerticalFeet": 1300,
        "LiftTime": "7:30",
    },
    {
        "Lift": "Lift 23",
        "Metadata": "Static Data",
        "ExperiencedRidersOnly": True,
        "VerticalFeet": 900,
        "LiftTime": "5:45",
    },
    {
        "Lift": "Lift 16",
        "Metadata": "Static Data",
        "ExperiencedRidersOnly": False,
        "VerticalFeet": 1500,
        "LiftTime": "9:00",
    },
    {
        "Lift": "Lift 10",
        "Metadata": "Static Data",
        "ExperiencedRidersOnly": True,
        "VerticalFeet": 1000,
        "LiftTime": "6:00",
    },
    # Lift days: one item per lift per date, ``Metadata`` is ``MM/DD/YY``.
    {
        "Lift": "Lift 3",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 5000,
        "AverageSnowCoverageInches": 30,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 23",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 1000,
        "AverageSnowCoverageInches": 45,
        "LiftStatus": "Open",
        "AvalancheDanger": "Considerable",
    },
    {
        "Lift": "Lift 16",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 4500,
        "AverageSnowCoverageInches": 35,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 10",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 0,
        "AverageSnowCoverageInches": 40,
        "LiftStatus": "Pending",
        "AvalancheDanger": "High",
    },
    {
        "Lift": "Lift 3",
        "Metadata": "02/01/20",
        "TotalUniqueLiftRiders": 6000,
        "AverageSnowCoverageInches": 35,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 23",
        "Metadata": "02/01/20",
        "TotalUniqueLiftRiders": 0,
        "AverageSnowCoverageInches": 50,
        "LiftStatus": "Closed",
        "AvalancheDanger": "Extreme",
    },
    {
        "Lift": "Lift 16",
        "Metadata": "02/01/20",
        "TotalUniqueLiftRiders": 5500,
        "AverageSnowCoverageInches": 40,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 10",
        "Metadata": "02/01/20",
        "TotalUniqueLiftRiders": 3500,
        "AverageSnowCoverageInches": 45,
        "LiftStatus": "Open",
        "AvalancheDanger": "Moderate",
    },
    {
        "Lift": "Lift 3",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 5500,
        "AverageSnowCoverageInches": 35,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 23",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 1500,
        "AverageSnowCoverageInches": 45,
        "LiftStatus": "Open",
        "AvalancheDanger": "Moderate",
    },
    {
        "Lift": "Lift 16",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 4000,
        "AverageSnowCoverageInches": 40,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    },
    {
        "Lift": "Lift 10",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 2500,
        "AverageSnowCoverageInches": 45,
        "LiftStatus": "Open",
        "AvalancheDanger": "Moderate",
    },
    # Resort days: the ``Resort Data`` partition has no ``LiftStatus`` and
    # ``OpenLifts`` is a number set, so duplicates collapse in the table.
    {
        "Lift": "Resort Data",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 5500,
        "AverageSnowCoverageInches": 35,
        "AvalancheDanger": "Considerable",
        "OpenLifts": [3, 23, 16],
    },
    {
        "Lift": "Resort Data",
        "Metadata": "02/01/20",
        "TotalUniqueLiftRiders": 6500,
        "AverageSnowCoverageInches": 45,
        "AvalancheDanger": "Moderate",
        "OpenLifts": [3, 16, 10],
    },
    {
        "Lift": "Resort Data",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 6000,
        "AverageSnowCoverageInches": 40,
        "AvalancheDanger": "Low",
        "OpenLifts": [3, 23, 16, 10],
    },
]
