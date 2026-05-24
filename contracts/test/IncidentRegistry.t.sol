// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import {IncidentRegistry} from "../src/registry/IncidentRegistry.sol";

contract IncidentRegistryTest is Test {
    IncidentRegistry public registry;

    address public governance = address(0x1001);
    address public reporter = address(0x2002);
    address public otherReporter = address(0x3003);
    address public attacker = address(0x4004);
    address public playbook = address(0x5005);

    bytes32 constant REPORT_HASH = keccak256("report");
    bytes32 constant IPFS_CID_HASH = keccak256("ipfs://cid");

    function setUp() public {
        registry = new IncidentRegistry(governance, reporter);
    }

    function test_fileIncident_success() public {
        vm.prank(reporter);
        bytes32 incidentId =
            registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 4, 4_200_000e18, 0, 10_000, true);

        assertEq(registry.incidentCount(), 1);
        assertEq(registry.incidentIdAt(0), incidentId);

        IncidentRegistry.Incident memory incident = registry.getIncident(incidentId);
        assertEq(incident.playbook, playbook);
        assertEq(incident.reporter, reporter);
        assertEq(incident.reportHash, REPORT_HASH);
        assertEq(incident.ipfsCidHash, IPFS_CID_HASH);
        assertEq(incident.signalCount, 4);
        assertEq(incident.protocolTvlBefore, 4_200_000e18);
        assertEq(incident.protocolTvlAfter, 0);
        assertEq(incident.pisBps, 10_000);
        assertTrue(incident.guardianActionTaken);
    }

    function test_fileIncident_revertsFromUnauthorizedReporter() public {
        vm.prank(attacker);
        vm.expectRevert(IncidentRegistry.NotAuthorizedReporter.selector);
        registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 4, 100e18, 0, 10_000, true);
    }

    function test_setReporterAuthorization_success() public {
        vm.prank(governance);
        registry.setReporterAuthorization(otherReporter, true);

        vm.prank(otherReporter);
        registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 3, 100e18, 90e18, 1_000, false);

        assertEq(registry.incidentCount(), 1);
    }

    function test_setReporterAuthorization_revertsFromNonGovernance() public {
        vm.prank(attacker);
        vm.expectRevert(IncidentRegistry.NotGovernance.selector);
        registry.setReporterAuthorization(otherReporter, true);
    }

    function test_fileIncident_revertsInvalidSignalCount() public {
        vm.prank(reporter);
        vm.expectRevert(IncidentRegistry.InvalidSignalCount.selector);
        registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 5, 100e18, 0, 10_000, true);
    }

    function test_fileIncident_revertsInvalidPIS() public {
        vm.prank(reporter);
        vm.expectRevert(IncidentRegistry.InvalidPIS.selector);
        registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 4, 100e18, 0, 10_001, true);
    }

    function test_fileIncident_revertsInvalidTVLDelta() public {
        vm.prank(reporter);
        vm.expectRevert(IncidentRegistry.InvalidTVLDelta.selector);
        registry.fileIncident(playbook, REPORT_HASH, IPFS_CID_HASH, 4, 100e18, 101e18, 0, false);
    }

    function test_getIncident_revertsUnknownIncident() public {
        bytes32 unknownIncidentId = keccak256("unknown");
        vm.expectRevert(abi.encodeWithSelector(IncidentRegistry.IncidentNotFound.selector, unknownIncidentId));
        registry.getIncident(unknownIncidentId);
    }

    function test_constructor_revertsZeroGovernance() public {
        vm.expectRevert(IncidentRegistry.ZeroAddress.selector);
        new IncidentRegistry(address(0), reporter);
    }

    function test_constructor_revertsZeroReporter() public {
        vm.expectRevert(IncidentRegistry.ZeroAddress.selector);
        new IncidentRegistry(governance, address(0));
    }
}
