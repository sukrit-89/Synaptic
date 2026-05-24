// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ISynapticGuardian} from "../interfaces/ISynapticGuardian.sol";

/// @title AMMPlaybook — Synaptic guardian playbook for AMM protocols
/// @notice Constrains what Synaptic can do: pause-only, rate-limited, governance-revocable
/// @dev Phase 1: signal count and TVL-at-risk are supplied by the off-chain consensus engine.
contract AMMPlaybook is ISynapticGuardian {
    // --- Roles ---
    address public immutable governance;
    address public synapticAddress;
    bool public synapticAccessRevoked;

    // --- State ---
    bool public guardianPaused;
    uint256 public pausedAt;
    uint256 public lastPauseTimestamp;

    // --- Constants ---
    uint256 public constant MIN_SIGNALS = 4;
    uint256 public constant MIN_TVL_AT_RISK = 100_000e18; // $100K (in protocol's unit)
    uint256 public constant MAX_PAUSES_PER_DAY = 1;
    uint256 public constant UNPAUSE_TIMELOCK = 24 hours;

    // --- Daily rate limit ---
    uint256 public pauseCountToday;
    uint256 public currentDayStart;

    // --- Errors ---
    error ZeroAddress();
    error SynapticAccessRevokedError();
    error NotSynaptic();
    error NotGovernance();
    error AlreadyPaused();
    error NotPaused();
    error TimelockNotElapsed(uint256 unlockTime);
    error PauseRateLimited(uint256 currentCount, uint256 maxPerDay);
    error InsufficientSignals(uint256 provided, uint256 required);
    error TVLBelowMinimum(uint256 tvlAtRisk, uint256 minimum);

    constructor(address _governance, address _synapticAddress) {
        if (_governance == address(0) || _synapticAddress == address(0)) {
            revert ZeroAddress();
        }
        governance = _governance;
        synapticAddress = _synapticAddress;
        currentDayStart = block.timestamp / 1 days * 1 days;
    }

    modifier onlySynaptic() {
        if (synapticAccessRevoked) revert SynapticAccessRevokedError();
        if (msg.sender != synapticAddress) revert NotSynaptic();
        _;
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert NotGovernance();
        _;
    }

    /// @notice Pause the protocol — Synaptic only
    /// @param signalCount Number of consensus signals active (must be >= 4)
    /// @param tvlAtRisk Estimated protocol value at risk, normalized to 18 decimals
    /// @param incidentHash On-chain hash of the incident report
    function guardianPause(uint256 signalCount, uint256 tvlAtRisk, bytes32 incidentHash)
        external
        override
        onlySynaptic
    {
        if (signalCount < MIN_SIGNALS) {
            revert InsufficientSignals(signalCount, MIN_SIGNALS);
        }

        if (tvlAtRisk < MIN_TVL_AT_RISK) {
            revert TVLBelowMinimum(tvlAtRisk, MIN_TVL_AT_RISK);
        }

        uint256 today = block.timestamp / 1 days * 1 days;
        if (today > currentDayStart) {
            pauseCountToday = 0;
            currentDayStart = today;
        }

        if (pauseCountToday >= MAX_PAUSES_PER_DAY) {
            revert PauseRateLimited(pauseCountToday, MAX_PAUSES_PER_DAY);
        }

        if (guardianPaused) revert AlreadyPaused();

        guardianPaused = true;
        pausedAt = block.timestamp;
        lastPauseTimestamp = block.timestamp;
        pauseCountToday++;

        emit GuardianPaused(msg.sender, signalCount, tvlAtRisk, incidentHash);
    }

    /// @notice Unpause — governance only, after timelock
    function guardianUnpause() external override onlyGovernance {
        if (!guardianPaused) revert NotPaused();

        uint256 unlockTime = pausedAt + UNPAUSE_TIMELOCK;
        if (block.timestamp < unlockTime) {
            revert TimelockNotElapsed(unlockTime);
        }

        guardianPaused = false;
        pausedAt = 0;

        emit GuardianUnpaused(msg.sender);
    }

    /// @notice Emergency: revoke Synaptic's access permanently
    /// @dev This cannot be undone — governance must deploy a new playbook
    function revokeSynapticAccess() external override onlyGovernance {
        synapticAccessRevoked = true;
        // Also unconditionally unpause so protocol isn't stuck
        guardianPaused = false;
        pausedAt = 0;

        emit SynapticAccessRevoked(msg.sender);
    }

    /// @notice Check if protocol is currently paused by Synaptic
    function isGuardianPaused() external view override returns (bool) {
        return guardianPaused;
    }

    /// @notice Time remaining on unpause timelock (0 if not paused or timelock elapsed)
    function timelockRemaining() external view returns (uint256) {
        if (!guardianPaused) return 0;
        uint256 unlockTime = pausedAt + UNPAUSE_TIMELOCK;
        if (block.timestamp >= unlockTime) return 0;
        return unlockTime - block.timestamp;
    }
}
