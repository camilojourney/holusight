export default function Home() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      {/* Nav */}
      <nav className="fixed top-0 w-full z-50 border-b border-gray-800/50 bg-[#0a0a0a]/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight">Holusight</span>
          <a
            href="#early-access"
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Request Early Access
          </a>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-40 pb-32 px-6 overflow-hidden">
        {/* Gradient glow */}
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-indigo-600/20 rounded-full blur-[120px] pointer-events-none" />

        <div className="relative max-w-4xl mx-auto text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-sm font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
            Enterprise AI Orchestration
          </div>

          {/* Headline */}
          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight leading-[1.1] mb-6">
            Federated AI Orchestration.{" "}
            <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
              Reliable by Design.
            </span>
          </h1>

          {/* Sub-headline */}
          <p className="text-lg text-gray-300 max-w-2xl mx-auto mb-10 leading-relaxed">
            Holus orchestrates multi-agent AI workflows with deterministic,
            phase-gated verification — so every output is traceable, measurable,
            and production-ready.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <a
              href="#early-access"
              className="px-6 py-3 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 font-medium hover:opacity-90 transition-opacity"
            >
              Request Early Access
            </a>
            <a
              href="#features"
              className="group flex items-center gap-2 text-gray-300 hover:text-white transition-colors font-medium"
            >
              See How It Works
              <svg
                className="w-4 h-4 group-hover:translate-x-0.5 transition-transform"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              Built for Enterprise-Grade AI
            </h2>
            <p className="text-gray-400 max-w-xl mx-auto">
              Every component of Holus is designed for production environments where
              accuracy, auditability, and reliability are non-negotiable.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Card 1 */}
            <div className="p-8 rounded-2xl bg-gray-900 border border-gray-800 hover:border-indigo-500/50 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center mb-5">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-3">Multi-Agent Orchestration</h3>
              <p className="text-gray-400 leading-relaxed">
                Coordinate specialized AI agents across complex workflows. Each agent
                handles what it does best, while Holus manages sequencing, handoffs,
                and failure recovery.
              </p>
            </div>

            {/* Card 2 */}
            <div className="p-8 rounded-2xl bg-gray-900 border border-gray-800 hover:border-violet-500/50 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center mb-5">
                <svg className="w-5 h-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-3">Phase-Gated Verification</h3>
              <p className="text-gray-400 leading-relaxed">
                Every pipeline stage requires passing verification gates before
                proceeding. No unverified outputs reach production — ever.
              </p>
            </div>

            {/* Card 3 */}
            <div className="p-8 rounded-2xl bg-gray-900 border border-gray-800 hover:border-indigo-500/50 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center mb-5">
                <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-3">Federated Deployment</h3>
              <p className="text-gray-400 leading-relaxed">
                Deploy AI capabilities across distributed systems without central
                bottlenecks. Each node operates independently, with full auditability.
              </p>
            </div>

            {/* Card 4 */}
            <div className="p-8 rounded-2xl bg-gray-900 border border-gray-800 hover:border-violet-500/50 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-violet-500/10 flex items-center justify-center mb-5">
                <svg className="w-5 h-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-3">Measurable Outputs</h3>
              <p className="text-gray-400 leading-relaxed">
                Every agent action is logged, scored, and traceable. Know exactly
                what your AI did, why it did it, and how to improve it.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="early-access" className="py-32 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-5">
            Ready to deploy AI that actually works?
          </h2>
          <p className="text-gray-400 text-lg mb-10 leading-relaxed">
            Holus is in early access. Join enterprises already building with
            deterministic AI.
          </p>
          <a
            href="mailto:hello@holusight.com"
            className="inline-block px-8 py-4 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-lg font-semibold hover:opacity-90 transition-opacity"
          >
            Request Early Access
          </a>
          <p className="mt-5 text-sm text-gray-500">
            No setup fee. Onboarding included.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-gray-800">
        <p className="text-center text-sm text-gray-500">
          © 2026 Holusight. All rights reserved.
        </p>
      </footer>
    </div>
  );
}
