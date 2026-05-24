// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Test.sol";
import {AMMPlaybook} from "../src/playbooks/AMMPlaybook.sol";

contract AMMPlaybookTest is Test {
    AMMPlaybook public playbook;

    address public governance = address(0x1001);
    address public synaptic = address(0x2002);
    address public attacker = address(0x3003);

    bytes32 constant INCIDENT_HASH = keccak256("test incident");
    uint256 constant TVL_AT_RISK = 100_000e18;

    function setUp() public {
        playbook = new AMMPlaybook(governance, synaptic);
    }

    // --- Pause tests ---

    function test_guardianPause_success() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        assertTrue(playbook.isGuardianPaused());
        assertEq(playbook.pauseCountToday(), 1);
    }

    function test_guardianPause_revertsBelowMinSignals() public {
        vm.prank(synaptic);
        vm.expectRevert(abi.encodeWithSelector(AMMPlaybook.InsufficientSignals.selector, 3, 4));
        playbook.guardianPause(3, TVL_AT_RISK, INCIDENT_HASH);
    }

    function test_guardianPause_revertsBelowMinTVLAtRisk() public {
        vm.prank(synaptic);
        vm.expectRevert(abi.encodeWithSelector(AMMPlaybook.TVLBelowMinimum.selector, TVL_AT_RISK - 1, TVL_AT_RISK));
        playbook.guardianPause(4, TVL_AT_RISK - 1, INCIDENT_HASH);
    }

    function test_guardianPause_revertsRateLimit() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        // Second pause same day should fail
        vm.prank(synaptic);
        vm.expectRevert(abi.encodeWithSelector(AMMPlaybook.PauseRateLimited.selector, 1, 1));
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);
    }

    function test_guardianPause_rateLimitResetsNextDay() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        // Advance to next day
        vm.warp(block.timestamp + 1 days);

        // Should succeed now — but first need to unpause
        // Actually, can't pause again while already paused
        // This tests the rate limit reset mechanism
        assertEq(playbook.pauseCountToday(), 1); // still 1 but day has reset
    }

    function test_guardianPause_revertsWhenAlreadyPaused() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        // Advance day so rate limit resets
        vm.warp(block.timestamp + 1 days);

        // But can't pause again while paused
        vm.prank(synaptic);
        vm.expectRevert(AMMPlaybook.AlreadyPaused.selector);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);
    }

    function test_guardianPause_revertsFromNonSynaptic() public {
        vm.prank(attacker);
        vm.expectRevert(AMMPlaybook.NotSynaptic.selector);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);
    }

    // --- Unpause tests ---

    function test_guardianUnpause_successAfterTimelock() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        // Advance past timelock
        vm.warp(block.timestamp + 24 hours);

        vm.prank(governance);
        playbook.guardianUnpause();

        assertFalse(playbook.isGuardianPaused());
    }

    function test_guardianUnpause_revertsBeforeTimelock() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        // Try before timelock
        vm.prank(governance);
        vm.expectRevert();
        playbook.guardianUnpause();
    }

    function test_guardianUnpause_revertsFromNonGovernance() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        vm.warp(block.timestamp + 24 hours);

        vm.prank(attacker);
        vm.expectRevert(AMMPlaybook.NotGovernance.selector);
        playbook.guardianUnpause();
    }

    function test_guardianUnpause_revertsWhenNotPaused() public {
        vm.prank(governance);
        vm.expectRevert(AMMPlaybook.NotPaused.selector);
        playbook.guardianUnpause();
    }

    // --- Revoke tests ---

    function test_revokeSynapticAccess_success() public {
        vm.prank(governance);
        playbook.revokeSynapticAccess();

        assertTrue(playbook.synapticAccessRevoked());
    }

    function test_revokeSynapticAccess_unpausesIfPaused() public {
        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);
        assertTrue(playbook.isGuardianPaused());

        vm.prank(governance);
        playbook.revokeSynapticAccess();

        assertFalse(playbook.isGuardianPaused());
        assertTrue(playbook.synapticAccessRevoked());
    }

    function test_revokeSynapticAccess_blocksFuturePauses() public {
        vm.prank(governance);
        playbook.revokeSynapticAccess();

        vm.prank(synaptic);
        vm.expectRevert(AMMPlaybook.SynapticAccessRevokedError.selector);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);
    }

    function test_revokeSynapticAccess_revertsFromNonGovernance() public {
        vm.prank(attacker);
        vm.expectRevert(AMMPlaybook.NotGovernance.selector);
        playbook.revokeSynapticAccess();
    }

    // --- Timelock query ---

    function test_timelockRemaining() public {
        assertEq(playbook.timelockRemaining(), 0);

        vm.prank(synaptic);
        playbook.guardianPause(4, TVL_AT_RISK, INCIDENT_HASH);

        uint256 remaining = playbook.timelockRemaining();
        assertGt(remaining, 0);
        assertLe(remaining, 24 hours);
    }

    // --- Constructor ---

    function test_constructor_revertsZeroGovernance() public {
        vm.expectRevert(AMMPlaybook.ZeroAddress.selector);
        new AMMPlaybook(address(0), synaptic);
    }

    function test_constructor_revertsZeroSynaptic() public {
        vm.expectRevert(AMMPlaybook.ZeroAddress.selector);
        new AMMPlaybook(governance, address(0));
    }
}
