// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title ISynapticGuardian — interface for Synaptic-compatible protocol contracts
/// @notice Protocol contracts implement this so Synaptic can trigger defensive actions
interface ISynapticGuardian {
    /// @notice Emitted when Synaptic triggers a pause
    event GuardianPaused(
        address indexed guardian, uint256 signalCount, uint256 tvlAtRisk, bytes32 indexed incidentHash
    );

    /// @notice Emitted when protocol is unpaused (requires governance + timelock)
    event GuardianUnpaused(address indexed governance);

    /// @notice Emitted when Synaptic's access is revoked by governance
    event SynapticAccessRevoked(address indexed governance);

    /// @notice Pause the protocol (called by authorized Synaptic address)
    /// @param signalCount Number of active signals that triggered this action
    /// @param tvlAtRisk Estimated protocol value at risk, normalized to 18 decimals
    /// @param incidentHash Hash of the incident report (for on-chain audit trail)
    function guardianPause(uint256 signalCount, uint256 tvlAtRisk, bytes32 incidentHash) external;

    /// @notice Unpause the protocol (governance only, after timelock)
    function guardianUnpause() external;

    /// @notice Check if protocol is currently paused by Synaptic
    function isGuardianPaused() external view returns (bool);

    /// @notice Revoke Synaptic's ability to pause (governance emergency action)
    function revokeSynapticAccess() external;
}
