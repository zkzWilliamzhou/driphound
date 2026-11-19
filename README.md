# Driphound

Financial data processing and analysis toolkit for transaction normalization and anomaly detection.

## Features

- **Transaction Normalization**: Process and standardize financial transactions from multiple sources
- **Currency Support**: Handles multiple currencies with proper minor unit calculations
- **Anomaly Detection**: Identify unusual spending patterns and potential issues
- **Data Deduplication**: Remove duplicate transactions automatically

## Installation

```bash
pip install -e .
```

## Usage

```python
from driphound.model import Tx, Statement

# Create transactions
tx = Tx(
    date="2024-01-15",
    amount_cents=-5000,  # $50.00 in cents
    currency="USD",
    merchant_raw="Starbucks",
    memo="Coffee",
    account="Chase Checking",
    source="CSV Import",
    line=5
)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## License

MIT © 2024 DripHound Contributors