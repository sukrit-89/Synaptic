// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "forge-std/Script.sol";
import {AMMPlaybook} from "../src/playbooks/AMMPlaybook.sol";

contract DeployAMMPlaybook is Script {
    function run() external {
        address governance = vm.envAddress("GOVERNANCE_ADDRESS");
        address synaptic = vm.envAddress("SYNAPTIC_ADDRESS");

        vm.startBroadcast();
        AMMPlaybook playbook = new AMMPlaybook(governance, synaptic);
        vm.stopBroadcast();

        console.log("AMMPlaybook deployed at:", address(playbook));
        console.log("Governance:", governance);
        console.log("Synaptic:", synaptic);
    }
}
