"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import type { User } from "@/lib/api";

export function Header() {
  const { theme, setTheme } = useTheme();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem("comio_user");
    if (stored) {
      try {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setUser(JSON.parse(stored));
      } catch {
        setUser(null);
      }
    }
  }, []);

  function handleSignOut() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("comio_token");
      window.localStorage.removeItem("comio_user");
    }
    setUser(null);
    router.push("/login");
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />

      <div className="flex-1" />

      {user ? (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-500 text-[11px] font-semibold text-white">
              {user.full_name?.charAt(0).toUpperCase() ??
                user.email.charAt(0).toUpperCase()}
            </div>
            <div className="hidden sm:flex flex-col">
              <span className="font-medium text-foreground">
                {user.full_name || user.email}
              </span>
              <span className="text-[10px] uppercase">{user.role}</span>
            </div>
          </div>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleSignOut}>
            Sign out
          </Button>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => router.push("/login")}
        >
          Sign in
        </Button>
      )}

      <Button
        variant="ghost"
        size="icon"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        aria-label="Toggle theme"
        className="ml-1"
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      </Button>
    </header>
  );
}
