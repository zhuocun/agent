"use client";

export interface WelcomeScreenProps {
  userName?: string;
}

function buildGreeting(userName?: string): string {
  const hour = new Date().getHours();
  const suffix = userName ? `, ${userName}` : "";

  if (hour >= 5 && hour <= 11) return `Good morning${suffix}`;
  if (hour >= 12 && hour <= 16) return `Good afternoon${suffix}`;
  if (hour >= 17 && hour <= 21) return `Good evening${suffix}`;
  return userName ? `Working late, ${userName}?` : "Working late?";
}

export function WelcomeScreen({ userName }: WelcomeScreenProps) {
  const heading = buildGreeting(userName);

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div className="flex flex-col items-center text-center animate-welcome-enter">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          {heading}
        </h1>
        <p className="mt-3 text-muted-foreground">
          What&apos;s on your mind?
        </p>
      </div>
    </div>
  );
}
