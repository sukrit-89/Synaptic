"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type EthereumProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

function shortenAddress(address: string) {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function WalletOptIn({
  compact = false,
  className = "",
}: {
  compact?: boolean;
  className?: string;
}) {
  const [address, setAddress] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "missing" | "error">("idle");

  useEffect(() => {
    const savedAddress = window.localStorage.getItem("synaptic_wallet");
    if (savedAddress) setAddress(savedAddress);
  }, []);

  const connectWallet = async () => {
    if (!window.ethereum) {
      setStatus("missing");
      return;
    }

    try {
      setStatus("connecting");
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      const firstAccount = Array.isArray(accounts) && typeof accounts[0] === "string" ? accounts[0] : null;

      if (!firstAccount) {
        setStatus("error");
        return;
      }

      setAddress(firstAccount);
      window.localStorage.setItem("synaptic_wallet", firstAccount);
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  };

  const disconnectWallet = () => {
    setAddress(null);
    setStatus("idle");
    window.localStorage.removeItem("synaptic_wallet");
  };

  if (address) {
    return (
      <Button
        type="button"
        variant="outline"
        size={compact ? "sm" : "lg"}
        onClick={disconnectWallet}
        className={`rounded-full border-foreground/20 bg-background/40 hover:bg-foreground/5 ${className}`}
      >
        {shortenAddress(address)}
      </Button>
    );
  }

  return (
    <div className={`flex flex-col items-start gap-2 ${className}`}>
      <Button
        type="button"
        size={compact ? "sm" : "lg"}
        onClick={connectWallet}
        className={`rounded-full bg-foreground text-background hover:bg-foreground/90 ${
          compact ? "px-4 h-8 text-xs" : "px-8 h-14 text-base"
        }`}
      >
        {status === "connecting" ? "Connecting..." : "Connect wallet"}
      </Button>
      {status === "missing" && (
        <span className="text-xs text-muted-foreground">Install MetaMask or Rabby to opt in.</span>
      )}
      {status === "error" && (
        <span className="text-xs text-muted-foreground">Wallet connection was rejected.</span>
      )}
    </div>
  );
}
