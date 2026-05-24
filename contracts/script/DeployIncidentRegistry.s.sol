// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";
import {IncidentRegistry} from "../src/registry/IncidentRegistry.sol";

contract DeployIncidentRegistry is Script {
    function run() external {
        address governance = vm.envAddress("GOVERNANCE_ADDRESS");
        address reporter = vm.envAddress("INCIDENT_REPORTER_ADDRESS");

        vm.startBroadcast();
        IncidentRegistry registry = new IncidentRegistry(governance, reporter);
        vm.stopBroadcast();

        console.log("IncidentRegistry deployed at:", address(registry));
        console.log("Governance:", governance);
        console.log("Initial reporter:", reporter);
    }
}
