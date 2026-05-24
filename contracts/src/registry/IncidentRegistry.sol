// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IncidentRegistry
/// @notice Immutable on-chain index of Synaptic incident reports and IPFS audit trails
contract IncidentRegistry {
    struct Incident {
        address playbook;
        address reporter;
        bytes32 reportHash;
        bytes32 ipfsCidHash;
        uint256 blockNumber;
        uint256 timestamp;
        uint8 signalCount;
        uint256 protocolTvlBefore;
        uint256 protocolTvlAfter;
        uint256 pisBps;
        bool guardianActionTaken;
    }

    address public immutable governance;
    mapping(address => bool) public authorizedReporter;
    mapping(bytes32 => Incident) private incidents;
    bytes32[] private incidentIds;

    event ReporterAuthorizationUpdated(address indexed reporter, bool authorized);
    event IncidentFiled(
        bytes32 indexed incidentId,
        address indexed playbook,
        address indexed reporter,
        bytes32 reportHash,
        bytes32 ipfsCidHash,
        uint8 signalCount,
        uint256 pisBps,
        bool guardianActionTaken
    );

    error ZeroAddress();
    error NotGovernance();
    error NotAuthorizedReporter();
    error InvalidSignalCount();
    error InvalidPIS();
    error InvalidTVLDelta();
    error IncidentAlreadyFiled(bytes32 incidentId);
    error IncidentNotFound(bytes32 incidentId);

    constructor(address _governance, address initialReporter) {
        if (_governance == address(0) || initialReporter == address(0)) {
            revert ZeroAddress();
        }

        governance = _governance;
        authorizedReporter[initialReporter] = true;

        emit ReporterAuthorizationUpdated(initialReporter, true);
    }

    modifier onlyGovernance() {
        if (msg.sender != governance) revert NotGovernance();
        _;
    }

    modifier onlyReporter() {
        if (!authorizedReporter[msg.sender]) revert NotAuthorizedReporter();
        _;
    }

    function setReporterAuthorization(address reporter, bool authorized) external onlyGovernance {
        if (reporter == address(0)) revert ZeroAddress();

        authorizedReporter[reporter] = authorized;
        emit ReporterAuthorizationUpdated(reporter, authorized);
    }

    function fileIncident(
        address playbook,
        bytes32 reportHash,
        bytes32 ipfsCidHash,
        uint8 signalCount,
        uint256 protocolTvlBefore,
        uint256 protocolTvlAfter,
        uint256 pisBps,
        bool guardianActionTaken
    ) external onlyReporter returns (bytes32 incidentId) {
        if (playbook == address(0)) revert ZeroAddress();
        if (signalCount > 4) revert InvalidSignalCount();
        if (pisBps > 10_000) revert InvalidPIS();
        if (protocolTvlAfter > protocolTvlBefore) revert InvalidTVLDelta();

        incidentId =
            keccak256(abi.encode(block.chainid, playbook, reportHash, ipfsCidHash, block.number, incidentIds.length));

        if (incidents[incidentId].timestamp != 0) {
            revert IncidentAlreadyFiled(incidentId);
        }

        incidents[incidentId] = Incident({
            playbook: playbook,
            reporter: msg.sender,
            reportHash: reportHash,
            ipfsCidHash: ipfsCidHash,
            blockNumber: block.number,
            timestamp: block.timestamp,
            signalCount: signalCount,
            protocolTvlBefore: protocolTvlBefore,
            protocolTvlAfter: protocolTvlAfter,
            pisBps: pisBps,
            guardianActionTaken: guardianActionTaken
        });
        incidentIds.push(incidentId);

        emit IncidentFiled(
            incidentId, playbook, msg.sender, reportHash, ipfsCidHash, signalCount, pisBps, guardianActionTaken
        );
    }

    function getIncident(bytes32 incidentId) external view returns (Incident memory incident) {
        incident = incidents[incidentId];
        if (incident.timestamp == 0) revert IncidentNotFound(incidentId);
    }

    function incidentCount() external view returns (uint256) {
        return incidentIds.length;
    }

    function incidentIdAt(uint256 index) external view returns (bytes32) {
        return incidentIds[index];
    }
}
