"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useGuestStore } from "@/store/guestStore";
import HotelHeader from "@/components/shared/HotelHeader";
import LoginForm from "@/components/guest/LoginForm";

export default function GuestLoginPage() {
  const { authenticated } = useGuestStore();
  const router = useRouter();

  useEffect(() => {
    if (authenticated) router.push("/guest/chat");
  }, [authenticated]);

  return (
    <div style={{ minHeight: "100vh" }}>
      <HotelHeader />
      <LoginForm />
    </div>
  );
}
