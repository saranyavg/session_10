# 🌌 Session Replay Viewer & Report

**Session ID**: `s8-db0f5ac8`
**Original Query**: Compare 5 AI coding tools by free plan and paid plan
**Timestamp**: 2026-06-21 16:17:28

## 1. Planner DAG
```
Planner (n:1) [complete]
```

## 2. Cost Ledger & Token Usage
| Agent | Provider | Calls | Tokens (In/Out) | USD Cost |
|---|---|---|---|---|
| browser | gemini | 33 | 33087 / 2836 | $0.000000 |
| critic | groq | 2 | 951 / 85 | $0.000206 |
| distiller | gemini | 2 | 5786 / 323 | $0.000000 |
| formatter | gemini | 1 | 1050 / 336 | $0.000000 |
| planner | gemini | 5 | 15275 / 1534 | $0.000000 |
| researcher | gemini | 5 | 10663 / 1352 | $0.000000 |
| **Total** | | **48** | **66812 / 6466** | **$0.000206** |

## 3. Browser Interaction Logs
### Browser Node `n:2` Details
- **URL**: https://www.g2.com/categories/ai-code-generation-tools
- **Goal**: Identify 5 popular AI coding tools and extract their free plan limitations and paid plan pricing/features.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://www.g2.com/categories/ai-code-generation-tools
- **Success**: `False`
- **Error**: all layers exhausted; last: giveup after 3 consecutive failures
### Browser Node `n:11` Details
- **URL**: https://cursor.com/pricing
- **Goal**: Extract details for Free and Pro plans.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://cursor.com/pricing
- **Success**: `True`

**Extracted Data Preview (first 2000 chars):**
```
Pricing
Hobby
Free
Includes:
- ✓ No credit card required
- ✓ Limited Agent requests
- ✓ Limited Tab completions
Download
Individual
$20 / mo.
Everything in Hobby, plus:
- ✓ Extended limits on Agent
- ✓ Access to frontier models
- ✓ MCPs, skills, and hooks
- ✓ Cloud agents
- ✓ Bugbot on usage-based billing
Teams
$40 / user / mo.
Everything on Individual, plus:
- ✓ Centralized team billing and administration
- ✓ Team marketplace for internal rules, skills, and plugins
- ✓ Agentic code reviews with Bugbot
- ✓ Cloud agents and automations with shared team context
- ✓ Usage analytics to understand team behavior
- ✓ Team-wide privacy mode
- ✓ SAML/OIDC SSO
Enterprise
Custom
Everything on Teams, plus:
- ✓ Pooled usage
- ✓ Invoice/PO billing
- ✓ SCIM seat management
- ✓ Repository, model, and MCP access controls
- ✓ Auto-run, browser, and network controls
- ✓ Audit logs and service accounts
- ✓ AI code tracking API
- ✓ Priority support and account management
Contact Sales
Trusted every day by teams that build world-class software.
Questions & Answers
We recommend Pro+ for daily agent users, and Ultra for agent power users. The Teams plan is recommended for professionals collaborating with others, and larger organizations that need invoicing, pooled usage, or advanced security should choose Enterprise.
Self-serve plans support all major credit and debit cards. For invoice-based billing and wire transfers, please
[contact us](https://cursor.com/contact-sales?source=pricing_faq)to discuss the Enterprise plan.Every plan includes a set amount of model usage. On-demand usage allows you to continue using models after your included amount is consumed, billed in arrears. See
[our docs](/docs/account/pricing)for more details.Admins can access usage information and key metrics through the
[Admin Dashboard](/docs/account/teams/dashboard).Privacy mode can be enabled in settings or by a team admin. When it is enabled, we guarantee that code data is not used for training by us or our mode...
```
### Browser Node `n:12` Details
- **URL**: https://github.com/features/copilot
- **Goal**: Find pricing page and extract Free vs Individual/Business plan differences.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://github.com/features/copilot
- **Success**: `True`

**Extracted Data Preview (first 2000 chars):**
```
Copilot in your editor does it all, from explaining concepts and completing code, to proposing edits and validating files with agent mode.
Command your craft
Your AI accelerator for every workflow, from the editor to the enterprise.
Companies using Copilot
Go beyond one-size-fits-all
Choose from leading LLMs optimized for speed, accuracy, or cost.
Use your agents, your way
Use GitHub Copilot, your own custom agents, or the third-party ones you already rely on.
Stay in your flow
Copilot works where you do—in GitHub, your IDE, project tools, chat apps, and custom MCP servers.
Code, command, and collaborate
AI that works where you do, whether in your editor, on the command line, or across GitHub.
Ship faster with AI that work alongside you
Assign tasks to agents like Copilot, Claude by Anthropic, and OpenAI Codex, and let them plan, explore, and execute work autonomously in the background.
Bring AI to your terminal workflow
Direct Copilot in the terminal using natural language and watch it plan, build, and execute complex workflows powered by your GitHub context.
Manage agent-driven work from one place
Launch work from GitHub, track progress across multiple agents, review changes, and merge completed work—all from one desktop workspace built natively on GitHub.
Grupo Boticário increases developer productivity by 94% with Copilot
[Read customer story](/customer-stories/grupoboticario)
Tailor-made for your organization
Shape Copilot to your business needs. Customize what it knows, how it acts, and where it connects.
[Turn Copilot into a project expert](/copilot/spaces)
Scale knowledge and keep teams consistent by creating a shared source of truth that includes context from your docs and repositories.
[Manage agent usage with enterprise-grade controls](https://docs.github.com/copilot/concepts/agents/enterprise-management)
Track activity with detailed audit logs and enforce governance by managing agents from a single control plane.
[Secure your MCP integrations](https://do...
```
### Browser Node `n:13` Details
- **URL**: https://sourcegraph.com/cody/pricing
- **Goal**: Extract Free vs Pro plan features.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://sourcegraph.com/cody/pricing
- **Success**: `False`
- **Error**: all layers exhausted; last: step cap reached (12)
### Browser Node `n:14` Details
- **URL**: https://www.tabnine.com/pricing
- **Goal**: Extract Free vs Pro plan features.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://www.tabnine.com/pricing/
- **Success**: `True`

**Extracted Data Preview (first 2000 chars):**
```
Tabnine named a Visionary
2026 Gartner® Magic Quadrant™
//
Pricing
//
Simple, clear, and transparent pricing for our private, secure AI-powered development platform optimized for your organization.
The Tabnine Code Assistant Platform provides high-quality code completions and AI chat grounded in your codebase, helping developers write, understand, and refactor code faster. Designed for teams that want immediate productivity gains, it integrates directly into popular IDEs and supports secure, enterprise-grade deployments.
39
per user per month
{ Annual subscription * }
- Code your way:
- AI code completions for current line and multiple lines for full-function implementation
- AI-powered chat in the IDE that supports every step in the SDLC,
using leading LLMs from Anthropic, OpenAI, Google, Meta, Mistral and others
- Works in all major IDEs
- Integration with Atlassian Jira Cloud and Data Center to inform AI responses and generation
- Flexible deployment options – SaaS, VPC, on-premises, or fully air-gapped. You choose where your code lives
- Zero code retention and total privacy – No storage, no training on your code, no sharing with third parties
- End-to-end encryption and TLS. Secure communication and data integrity in every environment
- SSO integration for ease of administration for private deployments
- Enterprise-grade compliance – Meets GDPR, SOC 2, ISO 27001, and more
- License-safe AI usage. Built-in protection against licensing risks**
- Fully private deployment on SaaS or self-hosted (VPC, on-premises, with the option to be fully air-gapped)
- Compatible with all major IDEs, LLMs, languages, and cloud providers
- Works across legacy systems and modern stacks
- No Lock-in and no forced tool changes
- Define clear boundaries and behaviors for the AI
- Governance controls to manage permissions, scope, and usage
- Centralized analytics for visibility into adoption, cost, and compliance
- Adjust Tabnine to follow your rules, processes, and risk profile
- Audi...
```
### Browser Node `n:15` Details
- **URL**: https://codeium.com/pricing
- **Goal**: Extract Free vs Pro plan features.
- **Path Chosen**: `EXTRACT`
- **Total Turns**: 0
- **Final URL**: https://devin.ai/pricing
- **Success**: `True`

**Extracted Data Preview (first 2000 chars):**
```
Plans and Pricing
Choose the perfect plan for your journey
INDIVIDUAL PLANS
Free
$0
Light quota to code with agents
Limited model availability
Unlimited inline edits
Unlimited Tab completions
ProPOPULAR
$20per month
Everything in Free, plus:
Increased quotas, including access to OpenAI, Claude, and Gemini frontier models
Full model availability
Free use of SWE 1.6 and leading open source models
Access to cloud agents (Devin Cloud)
Purchase extra usage at API pricing
TEAM PLANS
Teams
$80/month for team plan + $40/mo per full dev seat
Everything in Pro, plus:
Unlimited team members
Share and collaborate
Centralized billing
Admin dashboard with analytics
Priority support
Enterprise
Let's talk
Everything in Teams, plus:
Highest priority support
Dedicated account management
SAML/OIDC SSO
Centralized enterprise admin controls
Dedicated deployment option
First class support for every major model provider
Free$0/month
Pro$20/month
Max$200/month
Team$80/month
EnterpriseLet's talk
Members
1
1
1
Unlimited flex seats+$40/month per full userEach full user includes their own generous quota and access to Devin Desktop
Unlimited
Devin Desktop
Tab
Unlimited
Unlimited
Unlimited
Unlimited
Unlimited
Premium models
Fast context
Free SWE 1.6
Slow
Devin Cloud
DeepWiki
Devin API
Ask Devin
Advanced capabilities
Sharing and collaboration
Concurrent sessions limit
Up to 10
Up to 10
Unlimited
Unlimited
Integrations
Slack and Teams
Linear and Jira
GitHub, GitLab, and Bitbucket
Custom git provider support
Account support
Dedicated Slack Connect channel for support
Optional onboarding call with the Cognition team
Dedicated account and engineering support
Access to early feature releases and research previews
Custom
Dedicated account team
Custom terms
Enterprise accountsCentralized management of multiple Devin organizations
Security
Deploy in your virtual private cloud (VPC)
SAML/OIDC SSO
Centralized enterprise admin controls
Teamspace isolation
How does usage work?
Each paid plan comes with a usa...
```

## 4. Structured Data
### Extracted Structured Comparison Table


## 5. Final Answer
Here is a comparison of five prominent AI coding tools based on their free and paid offerings:

| Tool | Free Plan | Paid Plan | Best For |
| :--- | :--- | :--- | :--- |
| **GitHub Copilot** | Limited availability | ~$10/mo (Pro) | General developers in the Microsoft/GitHub ecosystem. |
| **Cursor** | Limited usage | ~$20/mo (Pro) | Power users needing agentic, multi-file editing in a dedicated IDE. |
| **Supermaven** | Available for individuals | High-performance focus | Developers prioritizing low-latency, high-speed autocomplete. |
| **Sourcegraph Cody** | No longer offered | ~$59/user/mo (Enterprise) | Large organizations needing multi-repo codebase intelligence. |
| **Tabnine** | Limited availability | Per-user/Enterprise pricing | Organizations with strict security, privacy, and compliance needs. |

Key takeaways:
- **GitHub Copilot** is the standard choice for individual productivity within the GitHub ecosystem.
- **Cursor** serves as a premium, AI-native IDE for complex, agent-driven coding tasks.
- **Sourcegraph Cody** and **Tabnine** are primarily focused on enterprise-grade features, security, and large-scale codebase management rather than individual developer plans.
- **Supermaven** differentiates itself through speed and latency optimization.

Sources: getdx.com, nxcode.io, aiagentslist.io, weavai.app
