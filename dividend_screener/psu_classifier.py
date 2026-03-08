"""Classify Indian listed companies as Public Sector (PSU) or Private Sector.

PSU = Public Sector Undertaking, where the Government of India (Central or State)
holds majority stake (>50%) or exercises management control.

This list covers Nifty 500 PSU companies as of 2025.
"""

# NSE symbols of known Public Sector Undertakings in Nifty 500
PSU_SYMBOLS = frozenset({
    # Banks (Public Sector Banks)
    "SBIN",          # State Bank of India
    "PNB",           # Punjab National Bank
    "BANKBARODA",    # Bank of Baroda
    "CANBK",         # Canara Bank
    "UNIONBANK",     # Union Bank of India
    "INDIANB",       # Indian Bank
    "BANKINDIA",     # Bank of India
    "MAHABANK",      # Bank of Maharashtra
    "UCOBANK",       # UCO Bank
    "IOB",           # Indian Overseas Bank
    "CENTRALBK",     # Central Bank of India
    "J&KBANK",       # Jammu & Kashmir Bank

    # Financial Services (PSU NBFCs / DFIs)
    "RECLTD",        # REC Limited
    "PFC",           # Power Finance Corporation
    "IRFC",          # Indian Railway Finance Corporation
    "HUDCO",         # Housing & Urban Development Corp
    "IDBI",          # IDBI Bank (LIC majority stake)
    "LICHSGFIN",     # LIC Housing Finance
    "LICI",          # Life Insurance Corporation
    "GICRE",         # General Insurance Corp
    "NIACL",         # New India Assurance
    "CANFINHOME",    # Can Fin Homes (Canara Bank subsidiary)

    # Oil & Gas
    "ONGC",          # Oil & Natural Gas Corporation
    "IOC",           # Indian Oil Corporation
    "BPCL",          # Bharat Petroleum
    "GAIL",          # GAIL (India)
    "OIL",           # Oil India
    "PETRONET",      # Petronet LNG
    "MRPL",          # Mangalore Refinery
    "CHENNPETRO",    # Chennai Petroleum

    # Mining & Metals
    "COALINDIA",     # Coal India
    "NMDC",          # NMDC
    "NATIONALUM",    # National Aluminium Company
    "HINDCOPPER",    # Hindustan Copper
    "MOIL",          # MOIL (Manganese Ore India)
    "KIOCL",         # KIOCL Limited

    # Power & Energy
    "NTPC",          # NTPC
    "POWERGRID",     # Power Grid Corporation
    "NHPC",          # NHPC
    "SJVN",          # SJVN
    "NREDCAP",       # NREDCAP (if listed)
    "NLCINDIA",      # NLC India

    # Defence & Aerospace
    "HAL",           # Hindustan Aeronautics
    "BEL",           # Bharat Electronics
    "BDL",           # Bharat Dynamics
    "MAZDOCK",       # Mazagon Dock Shipbuilders
    "COCHINSHIP",    # Cochin Shipyard
    "GRSE",          # Garden Reach Shipbuilders
    "MIDHANI",       # Mishra Dhatu Nigam

    # Infrastructure & Engineering
    "ENGINERSIN",    # Engineers India
    "NBCC",          # NBCC (India)
    "IRCON",         # Ircon International
    "RVNL",         # Rail Vikas Nigam
    "RAILTEL",       # RailTel Corporation
    "CONCOR",        # Container Corporation

    # Telecom & IT
    "MTNL",          # MTNL

    # Shipping & Logistics
    "GESHIP",        # Great Eastern Shipping (actually private)
    "SCI",           # Shipping Corp of India

    # Gas Distribution
    "IGL",           # Indraprastha Gas (joint with BPCL/GAIL)
    "MGL",           # Mahanagar Gas (joint with GAIL/Govt of Maharashtra)

    # Others
    "SAIL",          # Steel Authority of India
    "HFCL",         # HFCL (actually private now)
    "IRCTC",         # IRCTC
    "RITES",         # RITES
})

# Remove false positives (companies that are actually private)
_PRIVATE_OVERRIDES = {"GESHIP", "HFCL"}
PSU_SYMBOLS = PSU_SYMBOLS - _PRIVATE_OVERRIDES


def is_psu(nse_symbol: str) -> bool:
    """Check if a company is a Public Sector Undertaking."""
    return nse_symbol.upper() in PSU_SYMBOLS


def classify(nse_symbol: str) -> str:
    """Return 'PSU' or 'Private' for a given NSE symbol."""
    return "PSU" if is_psu(nse_symbol) else "Private"
