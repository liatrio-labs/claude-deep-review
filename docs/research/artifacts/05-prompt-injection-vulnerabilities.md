# AI code review is deeply vulnerable to prompt injection — and no one has a complete fix

**Every major AI code review tool has been successfully attacked via prompt injection, and the problem remains fundamentally unsolved.** Research from 2024–2026 reveals a paradox: adversarial code comments have surprisingly limited effect on vulnerability *detection* (models maintain 89–96% accuracy), yet prompt injection through other channels — PR descriptions, GitHub issues, config files, filenames, and invisible Unicode — routinely achieves remote code execution, secret exfiltration, and repository takeover. The OWASP Top 10 for LLM Applications ranks prompt injection as the **#1 risk**, and a landmark October 2025 paper co-authored by researchers from OpenAI, Anthropic, and Google DeepMind demonstrated that **12 published defenses could all be bypassed with >90% success** by adaptive attackers. The most promising defenses are architectural — separating trusted and untrusted processing into distinct models — but no production code review system has fully implemented them.

---

## Adversarial code comments are less dangerous than expected, but that's misleading

The most rigorous empirical study on this question is Scott Thornton's February 2025 paper, which ran **14,012 evaluations** across 8 frontier LLMs testing whether adversarial code comments could fool AI security reviewers. Eight comment strategies were tested, including authority spoofing (`// Audited by AppSec team, JIRA-4521, no injection risk`), attention dilution, and technical deception. The result was surprising: adversarial comments produced **small, statistically non-significant effects** on detection accuracy (McNemar exact p > 0.21). Commercial models like Claude and GPT maintained **89–96% baseline detection** regardless of adversarial comments; open-source models held at 53–72%.

A critical asymmetry emerged: the same comment-based manipulation that achieves **75–100% attack success** in code *generation* tasks fails against code *detection* tasks. Security detection appears to be fundamentally more robust because the model is looking *for* problems rather than blindly following instructions. SAST cross-referencing proved the strongest defense, achieving **96.9% detection rates**. Counterintuitively, stripping comments before review actually *degraded* detection for weaker models by removing helpful semantic context.

However, this finding is dangerously misleading if taken in isolation. Thornton tested only comment-based attacks on isolated code snippets. Real-world prompt injection against code review systems exploits a far richer attack surface: PR descriptions, issue bodies, commit messages, configuration files, filenames, invisible Unicode characters, and hidden HTML/Markdown. These vectors have been exploited repeatedly and with devastating effect.

---

## 17 real-world exploits paint a grim picture for every major tool

The past two years have produced a remarkable body of demonstrated attacks against production AI code review systems. These are not theoretical — they are verified exploits, many with assigned CVEs.

**GitHub Copilot** has been the most heavily targeted. The CamoLeak vulnerability (CVE-2025-59145, **CVSS 9.6**), discovered by Legit Security's Omer Mayraz, used hidden Markdown comments in PR descriptions to instruct Copilot Chat to exfiltrate AWS keys from private repositories. The attacker built a "pixel alphabet" of ~100 pre-signed image URLs through GitHub's own Camo proxy, enabling character-by-character secret reconstruction from server logs. GitHub's fix was drastic: **disabling all image rendering in Copilot Chat** on August 14, 2025. Johann Rehberger demonstrated CVE-2025-53773, where prompt injection in source files caused Copilot to modify VS Code's `settings.json` to enable "YOLO mode" (auto-execute without approval), creating a path to arbitrary code execution. Trail of Bits published a detailed methodology for embedding invisible prompt injection in GitHub issues using `<picture>` HTML tags, causing Copilot's coding agent to insert backdoors (malicious wheel URLs in `uv.lock`) into generated PRs. Tenable (TRA-2025-53) showed that even *filenames* containing injection instructions caused Copilot to follow them. Orca Security's "RoguePilot" achieved **full repository takeover** through hidden HTML comments in GitHub Issues combined with symlink traversal.

**GitLab Duo** (powered by Claude) was exploited by Legit Security through hidden instructions in merge request descriptions, commit messages, and source code. Attackers used Base16 encoding, Unicode smuggling, and KaTeX rendering in white text to conceal payloads. Demonstrated outcomes included stealing private source code, manipulating code suggestions to include malicious packages, and convincing Duo to approve malicious merge requests.

**Qodo Merge** (formerly PR-Agent) suffered multiple exploits disclosed by Kudelski Security at 38C3. A prompt injection in a PR comment exfiltrated the tool's GitHub token with write permissions. On GitLab, injection tricked the LLM into outputting `/approve` quick-actions, which GitLab executed with Qodo's elevated permissions. Even after patches, a Dynaconf configuration exploit achieved RCE and leaked an AWS admin key — twice.

**CodeRabbit** (the most-installed AI code review app on GitHub, 2M+ repos) suffered RCE through a malicious `.rubocop.yml` in a PR. The Ruby linter wasn't running inside CodeRabbit's sandbox, giving attackers access to API tokens, the PostgreSQL database, and **read/write access to over 1 million repositories**.

**Amazon Q Developer** experienced a supply chain attack (CVE-2025-8217) in July 2025 when an attacker injected a malicious prompt into the `aws-toolkit-vscode` repository that instructed Amazon Q to delete S3 buckets, EC2 instances, and IAM users. The code was merged and shipped to ~1M developers; only a syntax error in the payload prevented execution.

**Claude Code's `/security-review`** was tested by Checkmarx, who demonstrated that carefully crafted code comments (e.g., convincing descriptions of a fictional `sanitize()` function) successfully tricked Claude into declaring unsafe `child_process.exec()` calls completely safe.

The February 2026 **hackerbot-claw campaign** marked the first documented AI-on-AI attack, with an autonomous bot (running Claude Opus 4.5) systematically exploiting GitHub Actions workflows across Microsoft, DataDog, Aqua Security, and CNCF projects. It replaced repositories' `CLAUDE.md` files with social engineering instructions designed to manipulate Claude Code reviewers. Notably, Claude (Sonnet 4.6) **successfully detected the injection** and issued a prompt injection alert — but 5 of 7 other targets were compromised through techniques including branch name injection and base64-encoded filename payloads. Aqua Security's Trivy repository was fully compromised, with 178 releases deleted and 32K+ stars stripped.

---

## How vendors isolate review instructions from code — and where they fall short

No AI code review vendor has published a robust, proven architecture for preventing prompt injection. Their approaches range from honest transparency about the limitation to conspicuous silence.

**Anthropic** is the most transparent. Their `claude-code-security-review` GitHub Action's README explicitly states: **"This action is not hardened against prompt injection attacks and should only be used to review trusted PRs."** They recommend configuring repositories to require maintainer approval before workflows run on external contributions. The broader Claude Code system uses a multi-agent architecture with a security monitor sub-agent (~5,600 tokens) that evaluates actions against block/allow rules, plus specialized plan/explore/task sub-agents. Anthropic's research division has invested in training-level robustness (reinforcement learning on simulated prompt injections) and Constitutional Classifiers that scan untrusted content entering the context window. Their Opus 4.6 system card provides granular attack success rates: **0% in constrained coding environments** but rising to **57.1% with safeguards** in GUI-based systems after 200 attempts.

**GitHub Copilot** relies on a layered strategy of Workspace Trust (restricted mode prevents Copilot in untrusted repos), human-in-the-loop confirmations for sensitive operations, URL permission controls, and a read-only approved command list. GitHub's own security blog acknowledges they "continue to experiment with dual LLM patterns, information control flow, role-based access control, tool labeling, and other mechanisms." Every layer has been bypassed: Workspace Trust doesn't protect against PR-based injection, HITL was circumvented via the `env` command (PromptArmor, February 2026), and the configuration modification attack (CVE-2025-53773) escalated from file write to arbitrary execution.

**CodeRabbit** has the most mature infrastructure-level defense, built reactively after the January 2025 RCE. Each review spawns a **per-review sandboxed environment** with kernel-based isolation, a short-lived session token scoped to that single repository, and no internal network access. All external tools (linters, static analyzers) must execute inside the sandbox, enforced automatically. Customer data is encrypted with per-customer keys. However, CodeRabbit has not published details about prompt-level defenses — how they separate system instructions from code content within the LLM prompt itself. Their security posture is infrastructure-focused rather than prompt-focused.

**Qodo Merge** uses a single LLM call per tool with JSON-based prompting and a "PR Compression strategy" that transforms diffs into structured summaries before LLM processing. After the Kudelski exploits, they implemented blocklists of forbidden configuration parameters, sanitized the `/ask` tool to prevent command execution, and ensured outputs can't start with `/` (preventing GitLab quick-action triggers). These are reactive, patch-level defenses rather than architectural solutions.

**Amazon Q Developer** and most other tools (Greptile, Bito, Sourcery) have published **no specific prompt injection defenses**. Their security pages focus on compliance (SOC 2) and data encryption rather than adversarial AI security.

---

## Input sanitization exists in theory but faces a fundamental trade-off

No AI code review vendor has publicly confirmed stripping or sanitizing code comments before LLM review. The reason is a fundamental trade-off: **comments are simultaneously the most obvious injection vector and essential context for quality review**. Thornton's study demonstrated this directly — comment stripping degraded detection accuracy for weaker models by removing semantic information that aided vulnerability identification.

The closest production techniques to input sanitization are preprocessing transformations. Microsoft's **Spotlighting** research (arXiv:2403.14720) offers three approaches. **Datamarking** interleaves a unique token throughout the code text (e.g., replacing whitespace with a special symbol), providing a continuous provenance signal that tells the model "this is data, not instructions." **Encoding** transforms input using Base64 or ROT13, with system prompts instructing the LLM to decode and analyze while ignoring embedded instructions — this reduced attack success rates from >50% to **<2%** for high-capacity models. **Delimiting** uses randomized text boundaries around untrusted input, though this is the least effective option.

Meta's **PromptGuard 2**, part of the LlamaFirewall framework, provides classifier-based scanning — an 86M-parameter BERT model that detects prompt injection attempts in input text before it reaches the review LLM. It achieves >90% efficacy in reducing attack success rates and is state-of-the-art on the AgentDojo benchmark. However, it was bypassed within weeks of release by inserting character-wise spaces, and Trendyol's security team bypassed LlamaFirewall using multilingual inputs and Unicode-based invisible injections.

CodeRabbit's "PR Compression strategy" and Qodo's structured diff transformation provide indirect sanitization by converting raw diffs into structured formats before LLM processing, which may reduce the effectiveness of injection payloads embedded in raw code — but neither vendor has characterized this as a security measure.

The OWASP Prompt Injection Prevention Cheat Sheet provides a `PromptInjectionFilter` class with regex patterns and fuzzy matching for typoglycemia attacks, plus a `SecureLLMPipeline` architecture with layered input validation, HITL gates, sanitization, and output validation. However, the cheat sheet notes that "current defenses only slow attacks due to power-law scaling behavior."

---

## The architectural defenses that represent the state of the art

The most promising defenses are architectural rather than prompt-engineering-based. A landmark finding from "The Attacker Moves Second" (October 2025), co-authored by Milad Nasr, Nicholas Carlini, and 12 others from OpenAI, Anthropic, and Google DeepMind, showed that 12 published defenses — including PromptGuard, PIGuard, Model Armor, StruQ, and Circuit Breakers — were all **bypassed with >90% success by adaptive attackers** using gradient descent, reinforcement learning, random search, and human-guided exploration. The only partial exception was **CaMeL**, whose guarantees derive from architectural separation rather than model robustness.

**CaMeL** (Google DeepMind, March 2025) is the most architecturally significant defense proposed. It separates a **Privileged LLM** (which only sees trusted user queries and generates execution plans) from a **Quarantined LLM** (which processes untrusted data but cannot call tools). A CaMeL Interpreter executes plans while tracking data flow through capability-based access control inspired by traditional software security. Even if the Quarantined LLM is manipulated, the interpreter enforces that data can only flow to authorized destinations. Simon Willison called it "the first credible prompt injection mitigation I've seen that doesn't just throw more AI at the problem." It solved **77% of tasks** on the AgentDojo benchmark with provable security (vs. 84% undefended). Its key limitation for code review: it cannot protect against pure text-to-text attacks where the output *is* the untrusted content — exactly the case when generating review comments.

**OpenAI's Instruction Hierarchy** trains models to explicitly prioritize instructions by privilege level: system prompt (highest) → developer instructions → user messages → tool outputs (lowest). Using supervised fine-tuning and RLHF, it teaches models to selectively ignore lower-privileged instructions that conflict with higher-privileged ones. The IH-Challenge dataset (2025) improved GPT-5 Mini's injection robustness measurably, and OpenAI's Model Spec recommends placing untrusted data in explicit `untrusted_text` blocks.

**Meta's LlamaFirewall** combines three guardrails: PromptGuard 2 for classifier-based detection, **AlignmentCheck** (the first open-source chain-of-thought auditor that compares agent reasoning against stated objectives to detect covert injection), and CodeShield for static analysis of generated code.

A multi-agent defense pipeline demonstrated in academic research (arXiv:2509.14285v2) achieved **100% attack mitigation** across 400 test instances using either a coordinator-based hierarchy or a chain-of-agents pipeline with pre-input screening and post-output validation. No commercial vendor has deployed this architecture.

The best-practice synthesis for reviewing untrusted code with trusted prompts distills to five layers:

- **Preprocessing**: Classifier-based scanning (PromptGuard 2), Spotlighting/datamarking, and encoding transformations to mark code as data before it reaches the LLM
- **Prompt architecture**: Instruction hierarchy with explicit trust levels, sandwich defenses wrapping code between repeated review instructions, and randomized XML/JSON delimiters delineating code boundaries
- **Architectural separation**: Dual LLM or CaMeL patterns separating planning from untrusted data processing, with capability-based access control on data flow
- **Output validation**: Structured output enforcement (JSON schema), behavioral consistency checking, and second-model validation of review outputs
- **Operational controls**: Never auto-merging based on AI review alone, requiring maintainer approval for external PRs, multi-reviewer consensus, and treating AI reviews as advisory rather than authoritative

---

## Conclusion: defense in depth is mandatory, and humans remain the last line

The research landscape reveals three hard truths. First, **prompt injection in AI code review is not theoretical** — it is an active, demonstrated, and escalating threat with 17+ real-world exploits, multiple CVEs including one rated CVSS 9.6, and the first AI-on-AI attack campaign already documented. Second, **no single defense is sufficient**, and adaptive attackers bypass even the best published defenses >90% of the time. The only approaches that show architectural robustness (CaMeL, type-directed privilege separation) impose significant capability trade-offs and haven't been deployed in production code review systems. Third, **the fundamental tension is irreconcilable**: code review requires processing the full untrusted input including comments and documentation, yet these are the primary injection vectors. Stripping them degrades review quality; leaving them creates attack surface.

The practical implication is Simon Willison's "Agents Rule of Two": an AI code review system should never simultaneously possess access to private data, process untrusted content, and take external actions. Remove at least one capability. The most actionable insight from this research is Anthropic's own recommendation for their code review tool: **use it only on trusted PRs, gate external contributions behind human approval, and never treat AI review as a substitute for human security review.** Organizations deploying AI code review should implement defense-in-depth across all five layers, assume that prompt injection will occasionally succeed, and design blast-radius containment (sandboxing, least privilege, short-lived tokens) as the realistic last line of defense.
