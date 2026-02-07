"use client";

import { use, useState } from "react";
import {
  Send,
  FolderTree,
  GitBranch,
  RefreshCw,
  Play,
  Rocket,
  Square,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export default function SandboxPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [message, setMessage] = useState("");

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Left Panel — File Browser */}
      <Card className="w-80 flex-shrink-0 flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FolderTree className="h-4 w-4" />
              Files
            </CardTitle>
            <Badge variant="outline" className="text-xs">
              <GitBranch className="h-3 w-3 mr-1" />
              main
            </Badge>
          </div>
        </CardHeader>
        <Separator />
        <CardContent className="flex-1 p-3">
          <ScrollArea className="h-full">
            <p className="text-xs text-muted-foreground py-8 text-center">
              Start the sandbox to browse project files.
            </p>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Right Panel — Chat */}
      <Card className="flex-1 flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CardTitle className="text-sm font-medium">
                Sandbox Chat
              </CardTitle>
              <Badge
                variant="outline"
                className="text-xs bg-red-500/10 text-red-500 border-red-500/20"
              >
                Stopped
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button variant="outline" size="sm" className="h-8">
                <Rocket className="h-3 w-3 mr-1.5" />
                Deploy
              </Button>
              <Button variant="outline" size="sm" className="h-8">
                <Play className="h-3 w-3 mr-1.5" />
                Start
              </Button>
            </div>
          </div>
        </CardHeader>
        <Separator />

        {/* Messages Area */}
        <ScrollArea className="flex-1 p-4">
          <div className="flex flex-col items-center justify-center h-full py-16">
            <div className="flex items-center justify-center h-12 w-12 rounded-lg bg-orange-500/10 mb-4">
              <span className="text-orange-500 font-bold text-lg">C</span>
            </div>
            <h3 className="text-lg font-medium">Comio AI Assistant</h3>
            <p className="text-sm text-muted-foreground mt-1 text-center max-w-sm">
              Start the sandbox to chat with your AI assistant. It can create
              projects from scratch, edit code, run tests, and deploy — all
              through conversation.
            </p>
          </div>
        </ScrollArea>

        <Separator />

        {/* Input Area */}
        <div className="p-4">
          <div className="flex gap-2">
            <Input
              placeholder="Ask Comio to create, edit, deploy, or explain your code..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="flex-1"
              disabled
            />
            <Button size="icon" disabled>
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Project {id} · Start the sandbox to begin chatting
          </p>
        </div>
      </Card>
    </div>
  );
}
