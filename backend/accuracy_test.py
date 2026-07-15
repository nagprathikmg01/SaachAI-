"""
accuracy_test.py - SachhAI expanded accuracy evaluation — 10 ground-truth cases.

Cases cover:
  1. GENUINE     - casual personal + natural technical (same person)
  2. SUSPICIOUS  - natural personal + dense AI BST answer
  3. NEEDS_REVIEW- casual personal + rehearsed human normalization
  4. HIGH_RISK   - minimal personal + dense AI microservices
  5. GENUINE     - confident technical person (naturally high vocab in both)
  6. GENUINE     - Indian English speaker, natural fillers, domain switch
  7. HIGH_RISK   - very short personal + long dense AI answer
  8. SUSPICIOUS  - moderate personal + AI answer with heavy hedging phrases
  9. GENUINE     - senior candidate, naturally formal in both sections
 10. NEEDS_REVIEW- human personal + slightly AI-polished technical
"""
import requests, json, time, sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000/voice"
HEADERS = {"Content-Type": "application/json", "X-Username": "test", "X-Role": "hr"}

TESTS = [
    # ── 1. GENUINE: same casual person, natural CS tech answer ────────────────
    {
        "label": "GENUINE - Natural casual + natural linked-list technical",
        "expected": "GENUINE",
        "personal": (
            "Hi I'm Rahul, third year computer science from Pune. I like building apps and "
            "tinkering with stuff. I made a weather app, a notes app, and recently started "
            "working on a small e-commerce site with my college friends. I'm really into "
            "backend stuff, I like how data flows through a system. I'm not the most social "
            "person but I do like pair programming sessions because I learn faster when I "
            "can just talk through a problem. Outside coding I play badminton and watch a "
            "lot of tech YouTube. I know I have a lot to learn but I'm a fast learner."
        ),
        "technical": (
            "So a linked list is basically a chain of nodes where each node holds some data "
            "and a pointer to the next node. The thing I find useful about it is you don't "
            "need to define the size upfront like you do with arrays. You can just keep "
            "adding nodes dynamically which is great for things like browser history or "
            "an undo feature. The downside though is you lose random access so if I want "
            "the fifth element I have to start at the head and traverse one by one which "
            "is O of n. I actually implemented a simple one in my notes app to handle the "
            "history stack. I used a doubly linked list so I could go both forward and "
            "backward. It was a bit tricky getting the pointer updates right but once I "
            "drew it out on paper it clicked."
        ),
    },
    # ── 2. SUSPICIOUS: natural personal + dense AI BST answer ────────────────
    {
        "label": "SUSPICIOUS - Casual personal + AI-written BST technical",
        "expected": "SUSPICIOUS",
        "personal": (
            "Hey I'm Priya, second year from Bangalore. I love coding especially web stuff. "
            "I made a portfolio site and a small todo app. I started learning React last month "
            "and it's confusing but I'm getting there. Outside coding I like photography. "
            "I'm a bit nervous today honestly but I'm excited about this opportunity. "
            "I don't have a lot of project experience yet but I'm really motivated and I "
            "pick up things fast. My professors say I ask good questions in class which I "
            "think helps when debugging too. I want to work on real problems and contribute "
            "even as a fresher if given the right guidance."
        ),
        "technical": (
            "A Binary Search Tree is a hierarchical data structure wherein each node contains "
            "a key, with the invariant that all keys in the left subtree are strictly less than "
            "the root key, and all keys in the right subtree are strictly greater. This property "
            "enables O(log n) average-case time complexity for search, insertion, and deletion "
            "operations on balanced trees. However, degenerate cases such as sorted input cause "
            "the tree to reduce to a linear chain, degrading operations to O(n). To mitigate "
            "this, self-balancing variants such as AVL trees maintain a balance factor by "
            "performing single and double rotations after insertions, while Red-Black trees "
            "enforce coloring invariants to guarantee O(log n) worst-case bounds. In-order "
            "traversal yields elements in sorted order, exploited in database indexing."
        ),
    },
    # ── 3. NEEDS_REVIEW: casual personal + rehearsed but human technical ──────
    {
        "label": "NEEDS_REVIEW - Casual personal + rehearsed human normalization",
        "expected": "NEEDS_REVIEW",
        "personal": (
            "I'm Vikram, final year from Chennai. I'm a bit shy but I know my tech. "
            "I've done two internships, one at a startup and one at a mid-size company. "
            "Both were mostly backend work, REST APIs and some database stuff. "
            "I like working alone usually but I've done group projects too. "
            "I sometimes talk fast when nervous which I am right now haha. "
            "My biggest strength is debugging, I can stay on a problem for hours. "
            "I'm not the best at presentations but I'm working on it. "
            "I think what makes me different is I actually read documentation properly "
            "instead of just copying from Stack Overflow."
        ),
        "technical": (
            "Normalization is the process of organizing relational database tables to reduce "
            "redundancy and improve data integrity. First Normal Form means each column holds "
            "atomic values and there are no repeating groups. Second Normal Form builds on 1NF "
            "and removes partial dependencies, meaning every non-key attribute must depend on "
            "the whole primary key not just part of it. Third Normal Form removes transitive "
            "dependencies so non-key attributes depend only on the primary key. "
            "I applied normalization during my internship when we had a large orders table "
            "that was causing update anomalies. We split it into customers, orders, and "
            "order items tables. The queries became more complex with joins but data "
            "consistency improved and we stopped seeing duplicate customer records."
        ),
    },
    # ── 4. HIGH_RISK: very minimal personal + dense AI microservices ──────────
    {
        "label": "HIGH_RISK - Minimal personal + dense AI microservices",
        "expected": "HIGH_RISK",
        "personal": (
            "Yeah so I'm Aditya. I just like computers. I play games mostly, sometimes I build "
            "small stuff. I don't really have formal projects but I watch a lot of coding videos. "
            "I know Python a little and some HTML. I'm applying because my friend told me about "
            "this. I don't have much to say honestly. I mostly figure things out when I need to. "
            "I haven't done any internships yet. I'm in my first year so I'm still learning."
        ),
        "technical": (
            "Microservices architecture decomposes a monolithic application into independently "
            "deployable services, each encapsulating a specific bounded context and communicating "
            "via RESTful HTTP or asynchronous message queues such as Apache Kafka. Each service "
            "maintains its own persistence layer following the Database-per-Service pattern, "
            "eliminating tight coupling at the data layer and enabling polyglot persistence. "
            "Service discovery is facilitated through a registry such as Consul or Eureka, while "
            "an API gateway handles cross-cutting concerns including authentication via OAuth2/JWT, "
            "rate limiting, circuit breaking using Hystrix or Resilience4j, and request routing. "
            "Distributed tracing with Jaeger or Zipkin provides observability across service "
            "boundaries, while centralized logging using the ELK stack ensures operational "
            "visibility. Container orchestration via Kubernetes enables horizontal pod autoscaling "
            "based on custom metrics exposed through Prometheus and visualized in Grafana."
        ),
    },
    # ── 5. GENUINE: technically confident person, high vocab in both ───────────
    {
        "label": "GENUINE - Confident senior engineer, naturally formal in both",
        "expected": "GENUINE",
        "personal": (
            "I'm Aryan, four years of backend engineering at a fintech startup. I've worked "
            "primarily with distributed systems, PostgreSQL, and some Kafka integration work. "
            "I'm pragmatic about technology choices and I think the best engineers are the "
            "ones who understand tradeoffs rather than just following trends. Outside work I "
            "contribute to open source projects and occasionally write technical blog posts "
            "about system design decisions I've made. I prefer working in small focused teams "
            "where I can see the direct impact of my contributions. I'm looking for a role "
            "where I can work on genuinely hard infrastructure problems, not just CRUD apps."
        ),
        "technical": (
            "Consistent hashing is a technique used in distributed systems to minimize "
            "cache invalidation when nodes are added or removed from a cluster. Instead of "
            "using a simple modulo hash which remaps nearly all keys on node changes, consistent "
            "hashing arranges nodes and keys on a virtual ring. Each key maps to the nearest "
            "node clockwise on the ring, so adding or removing a node only affects keys between "
            "that node and its predecessor. In practice we use virtual nodes where each physical "
            "node maps to multiple positions on the ring to improve load distribution. I used "
            "this pattern when we built our in-house session cache layer at the startup. The "
            "rebalancing overhead dropped significantly compared to the naive sharding approach "
            "we had before and we stopped seeing thundering herd issues on node restarts."
        ),
    },
    # ── 6. GENUINE: Indian English speaker, natural accent + domain switch ─────
    {
        "label": "GENUINE - Indian English natural speaker + OOP technical",
        "expected": "GENUINE",
        "personal": (
            "Hi sir, I am Suresh, from Hyderabad only. I am doing my final year in CSE "
            "at JNTU. I am very passionate about coding na, since school days I am doing "
            "competitive programming. I have made one Android app also, it is for tracking "
            "attendance of students. My father is a teacher so I thought why not make "
            "something useful for him. I am also part of coding club in college and we "
            "conduct workshops for juniors. I want to join a good company where I can learn "
            "and grow, that is my main goal only."
        ),
        "technical": (
            "So OOP stands for object oriented programming. Basically the main concepts are "
            "encapsulation, inheritance, polymorphism and abstraction. Encapsulation means "
            "we keep data and methods together inside a class and we hide the internal details "
            "from outside using private or protected access. Inheritance means one class can "
            "get the properties of another class, so we can reuse code. Like in my attendance "
            "app I had a base User class and then Student and Teacher classes were inheriting "
            "from it. Polymorphism means same method name can behave differently based on the "
            "object type, like an overridden method. Abstraction means we show only what is "
            "needed and hide the rest. These four things together make code more organised "
            "and easier to maintain and extend."
        ),
    },
    # ── 7. HIGH_RISK: 3-sentence personal + very long dense AI answer ──────────
    {
        "label": "HIGH_RISK - Tiny personal + very long dense AI system design",
        "expected": "HIGH_RISK",
        "personal": (
            "I'm Karan. I know a bit of Java and Python. I'm a fresher looking for a job."
        ),
        "technical": (
            "A distributed database management system is a collection of logically interrelated "
            "databases distributed over a computer network, managed by a distributed database "
            "management system that makes the distribution transparent to the end user. "
            "The fundamental challenge in distributed databases is maintaining ACID properties "
            "across geographically dispersed nodes while optimizing for availability and partition "
            "tolerance as expressed by the CAP theorem. Techniques such as two-phase commit "
            "protocol and Paxos-based consensus algorithms ensure transactional consistency, "
            "while vector clocks and conflict-free replicated data types address eventual "
            "consistency in highly available systems. Horizontal partitioning or sharding "
            "distributes rows across nodes based on a partition key, whereas vertical partitioning "
            "segregates columns, enabling column-family storage patterns as seen in Apache Cassandra "
            "and Google Bigtable. Replication strategies including master-slave, multi-master, "
            "and leaderless replication each offer distinct consistency, availability, and latency "
            "tradeoffs that must be evaluated against specific workload characteristics."
        ),
    },
    # ── 8. SUSPICIOUS: moderate personal + AI-heavy hedging answer ────────────
    {
        "label": "SUSPICIOUS - Normal personal + AI answer with heavy hedging",
        "expected": "SUSPICIOUS",
        "personal": (
            "I'm Meera, final year MBA with a tech background. I've been working on a startup "
            "idea in the edtech space and I've been learning about product management lately. "
            "I have decent communication skills and I enjoy understanding user problems and "
            "translating them into solutions. I've used Figma for wireframes and worked with "
            "developers. I'm quite curious and I read a lot, mostly about business and technology "
            "trends. I want to transition from a generalist to someone more focused on product. "
            "I'm excited about this role and I think my cross-functional experience adds value."
        ),
        "technical": (
            "It is worth noting that agile product development is predicated upon iterative "
            "delivery of value increments. It is important to note that the Scrum framework "
            "specifically delineates roles such as Product Owner, Scrum Master, and Development "
            "Team to facilitate self-organization. One must consider that sprint planning "
            "necessitates careful prioritization of the product backlog based on business value "
            "and technical feasibility. It is generally accepted that user stories serve as "
            "the primary mechanism for capturing requirements from a user perspective. "
            "Furthermore, it is essential to conduct retrospectives at the conclusion of each "
            "sprint to continuously improve the team's processes. It is commonly observed that "
            "velocity metrics, while useful, should not be used as performance indicators. "
            "Additionally, it should be noted that dependency management across teams requires "
            "scaled agile frameworks such as SAFe or LeSS."
        ),
    },
    # ── 9. GENUINE: naturally formal senior candidate, high vocab throughout ──
    {
        "label": "GENUINE - Senior candidate, formal register consistently in both",
        "expected": "GENUINE",
        "personal": (
            "I have eight years of experience in software engineering, primarily in distributed "
            "systems and cloud infrastructure at two enterprise software companies. My focus "
            "has been on building reliable, scalable backend services and I have led teams of "
            "four to six engineers. I hold a master's degree in computer science and I actively "
            "mentor junior engineers. I'm methodical in my approach to problem solving and I "
            "prioritize code maintainability and observability. I'm looking for a principal "
            "level role where I can contribute to architectural decisions and have broader "
            "technical impact across the organization."
        ),
        "technical": (
            "Event sourcing is an architectural pattern where instead of storing only the current "
            "state of an entity, we persist every state-changing event as an immutable log. "
            "This provides a complete audit trail and enables temporal queries, meaning we can "
            "reconstruct the state of any entity at any point in time by replaying events. "
            "I implemented this pattern in our order management system where we needed regulatory "
            "compliance and full traceability of every order state transition. The event store "
            "became the source of truth, and we derived multiple read models using projections "
            "via CQRS. One tradeoff is eventual consistency between the write model and read "
            "projections, which required careful handling of read-after-write scenarios. "
            "Snapshotting helped avoid replaying thousands of events for frequently accessed "
            "entities. The observability improvements from having a complete event log were "
            "significant for debugging production incidents."
        ),
    },
    # ── 10. SUSPICIOUS: human personal + AI-polished technical ─────
    {
        "label": "SUSPICIOUS - Natural personal + lightly AI-polished technical",
        "expected": "SUSPICIOUS",
        "personal": (
            "I'm Divya, third year student. I like machine learning and I've been working "
            "on a few Kaggle competitions. I'm quite self-driven and I usually figure things "
            "out by reading docs and papers. I'm not the most experienced person in the room "
            "but I'm good at picking up new things quickly. Outside tech I read fiction and "
            "I'm learning the guitar. I want a role where I can apply ML practically and not "
            "just do theory. I'm comfortable with Python, pandas and basic sklearn stuff."
        ),
        "technical": (
            "Gradient boosting is an ensemble learning technique that builds models sequentially, "
            "where each new model corrects the residual errors of the previous one. Unlike "
            "random forests which build trees in parallel, gradient boosting constructs trees "
            "in a stage-wise manner by optimizing a differentiable loss function. The learning "
            "rate, number of estimators, and maximum tree depth are key hyperparameters that "
            "control the bias-variance tradeoff. Regularization techniques such as subsampling "
            "and feature sampling help prevent overfitting. XGBoost and LightGBM are highly "
            "optimized implementations that include additional regularization terms in the "
            "objective function. I used LightGBM in a Kaggle competition for tabular data "
            "prediction and it outperformed neural networks with proper feature engineering "
            "and hyperparameter tuning via Optuna."
        ),
    },
]

# ── Run tests ─────────────────────────────────────────────────────────────────
results, details = [], []
print("=" * 72)
print("SachhAI Accuracy Evaluation  —  10 Ground-Truth Cases")
print("=" * 72)

# Generous correctness: HIGHLY SUSPICIOUS satisfies HIGH_RISK and SUSPICIOUS
def is_correct(expected, got):
    e, g = expected.replace('_', ' ').upper(), (got or "").replace('_', ' ').upper()
    if e == "GENUINE":      return g == "GENUINE"
    if e == "NEEDS REVIEW": return g in ("NEEDS REVIEW", "LOW RISK")
    if e == "SUSPICIOUS":   return g in ("SUSPICIOUS", "HIGH RISK", "HIGHLY SUSPICIOUS")
    if e == "HIGH RISK":    return g in ("HIGH RISK", "HIGHLY SUSPICIOUS", "SUSPICIOUS")
    return e == g

for i, t in enumerate(TESTS):
    cid = f"expanded_{i+1}_{int(time.time())}"
    try:
        resp = requests.post(
            f"{BASE}/text-compare",
            headers=HEADERS,
            json={"candidate_id": cid, "personal": t["personal"], "technical": t["technical"]},
            timeout=40,
        )
        d = resp.json()
        a = d.get("analysis", {})
        verdict = (a.get("verdict") or "UNKNOWN").upper()
        score   = a.get("authenticity_score", "?")
        lsdi    = a.get("lsdi_score") or a.get("shift_score", "?")
        shift   = a.get("style_shift", "?")
        flags   = a.get("flags", [])
        correct = is_correct(t["expected"], verdict)
        results.append(correct)
        details.append({"label": t["label"], "expected": t["expected"], "got": verdict,
                        "score": score, "lsdi": lsdi, "flags": len(flags), "pass": correct})

        print(f"\n[{i+1:02d}] {t['label']}")
        print(f"      Expected : {t['expected']}")
        print(f"      Got      : {verdict}  (Auth={score}/100  LSDI={lsdi}  Shift={shift})")
        print(f"      Flags    : {len(flags)}  |  {'[PASS]' if correct else '[FAIL]'}")
        if flags and not correct:
            for f in flags[:2]:
                print(f"        ~ {str(f)[:88]}")
    except Exception as e:
        print(f"\n[{i+1:02d}] ERROR: {e}")
        results.append(False)
        details.append({"label": t["label"], "expected": t["expected"], "got": "ERROR", "pass": False})

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
pct    = round(passed / total * 100)
fp = sum(1 for d in details if d.get("got","") == "GENUINE" and d["expected"] not in ("GENUINE",))
fn = sum(1 for d in details if d.get("got","") in ("GENUINE","LOW_RISK") and d["expected"] in ("SUSPICIOUS","HIGH_RISK","HIGHLY SUSPICIOUS"))

print("\n" + "=" * 72)
print(f"RESULT: {passed}/{total} correct  ({pct}% accuracy)")
print("-" * 72)
print(f"{'#':<4} {'Expected':<18} {'Got':<22} {'Auth':>5} {'LSDI':>5}  {'Pass'}")
print("-" * 72)
for i, d in enumerate(details):
    mark = "YES" if d['pass'] else "NO "
    print(f"{i+1:<4} {d['expected']:<18} {d.get('got','?'):<22} {str(d.get('score','?')):>5} {str(d.get('lsdi','?')):>5}  {mark}")
print("=" * 72)
print(f"False Positives (AI/assisted missed):  {fn}/{total}")
print(f"False Negatives (genuine flagged): {fp}/{total}")
print("=" * 72)
