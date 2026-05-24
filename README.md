# Synaptic

**Everyone else matches signatures. Synaptic simulates consequences.**

Synaptic is a simulation-first DeFi security layer that watches the attack window, simulates what a suspicious transaction would do to protocol state, scores the economic impact, and triggers governance-safe defenses only when the evidence is strong enough.

The project combines:

- **Solidity playbooks** that constrain emergency actions on-chain
- **An on-chain incident registry** for auditability and insurance evidence
- **A Python/FastAPI backend** for mempool parsing, signal generation, and consensus decisions
- **A Next.js frontend** that presents the product, demo flow, playbooks, PRS story, and revenue model

## Why Synaptic

Most DeFi monitoring tools detect patterns. Synaptic detects outcomes.

The core product promise is simple:

1. Watch mempool and block activity.
2. Run multiple independent risk signals.
3. Fork current chain state and simulate the suspicious transaction.
4. Compute Protocol Impact Score (PIS).
5. Execute only the protocol-approved response path.
6. File an auditable incident trail for governance and insurers.

Autonomous pause is deliberately hard to trigger: the AMM playbook requires 4 active signals, minimum TVL at risk, and a daily rate limit.

## Repository Layout

```text
.
├── backend/                                  # FastAPI, Celery, Redis, simulation and signal code
│   ├── synaptic/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── contracts/                                # Foundry Solidity contracts and tests
│   ├── src/
│   │   ├── interfaces/ISynapticGuardian.sol
│   │   ├── playbooks/AMMPlaybook.sol
│   │   ├── registry/IncidentRegistry.sol
│   │   └── mocks/MockERC20.sol
│   ├── script/
│   ├── test/
│   └── foundry.toml
├── optimus-the-ai-platform-to-build-and-ship/ # Synaptic frontend built on the Optimus/v0 UI shell
├── docker-compose.yml
└── .env.example
```

## Product Surface

### Four Signals

- **Signal 1: Rule-based heuristics**  
  Fast checks for flash-loan drain patterns, reserve ratio spikes, and same-block profit extraction.

- **Signal 2: Anomaly model**  
  IsolationForest plus statistical ensemble. Current PRD benchmark: 97.08% detection.

- **Signal 3: Counterfactual simulation**  
  Fork state, execute the suspicious transaction in a sandbox, then compute:

  ```text
  PIS = (protocol_tvl_before - protocol_tvl_after) / protocol_tvl_before
  ```

- **Signal 4: Protocol invariant check**  
  AMM, money market, and perp-specific invariants that catch protocol-class failures.

### On-Chain Trust Layer

The contracts encode the governance trust argument directly:

- `AMMPlaybook.sol`
  - Pause-only authority
  - 4-signal threshold
  - minimum `$100K` TVL at risk
  - max 1 autonomous pause per day
  - governance-only unpause after 24 hours
  - governance can revoke Synaptic access

- `IncidentRegistry.sol`
  - Stores report hash, IPFS CID hash, signal count, PIS, TVL delta, reporter, block number, and whether guardian action was taken
  - Creates an immutable audit trail for governance and insurance review

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/sukrit-89/Synaptic.git
cd Synaptic
cp .env.example .env
```

Fill in the chain/provider values in `.env`.

### 2. Run the frontend

```bash
cd optimus-the-ai-platform-to-build-and-ship
npm install
npm run dev
```

Open `http://localhost:3000`.

Useful checks:

```bash
npm run lint
npx tsc --noEmit
npm run build
```

### 3. Run the Solidity tests

Install Foundry, then install the test dependency:

```bash
cd contracts
forge install foundry-rs/forge-std
forge test
```

### 4. Run the backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### 5. Run services with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

This starts Redis, the FastAPI service, and Celery workers.

## Demo Story

The intended 45-second demo:

1. Show a vulnerable AMM with `$4.2M` TVL.
2. Launch a novel flash-loan variant.
3. Signals fire:
   - reserve spike
   - anomaly ensemble
   - PIS showing near-total drain
   - AMM invariant violation
4. `AMMPlaybook.guardianPause(...)` executes.
5. Attack transaction reverts with `Paused`.
6. `IncidentRegistry` files an on-chain report tied to IPFS evidence.

The point is not “AI detected something.” The point is:

> If this transaction executes, this much money disappears. Therefore the constrained playbook response is justified.

## Current Status

Validated locally:

- Frontend lint
- Frontend TypeScript
- Frontend production build
- Foundry contract tests

Known product priorities from the PRD:

1. Fix counter-tx failure rate by making guardian pause and counter-tx independent paths.
2. Expand playbooks beyond AMM to money markets and perp DEXs.
3. Wire backend incident filing to the on-chain registry plus IPFS.
4. Add LLM reasoning traces.
5. Build PRS computation and insurer API.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Contracts | Solidity 0.8.x, Foundry |
| Backend | Python 3.11, FastAPI, Celery, Redis, Web3.py |
| Simulation | Anvil fork pool, Tenderly fallback planned |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, shadcn/ui-style components |
| Reporting | On-chain incident registry, IPFS hash storage |
| Risk data | PRS API and Chainlink-compatible oracle planned |

## Safety Philosophy

Synaptic is designed to be safe by default:

- off-chain services can reason and recommend,
- on-chain playbooks constrain what can actually happen,
- governance can revoke access,
- every material action leaves an audit trail.

That is the core trust argument for protocols and insurers.
