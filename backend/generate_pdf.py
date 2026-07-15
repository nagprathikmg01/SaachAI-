import requests
import json
import time
import sys
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor

BASE_URL = "http://127.0.0.1:8000/voice/text-compare"
HEADERS = {"Content-Type": "application/json", "X-Username": "admin", "X-Role": "admin"}

TEST_CASES = [
    {
        "name": "1. Genuine Junior Candidate",
        "personal": "Hi, I'm Rahul. I just finished my degree. I like building simple web apps and playing video games. I'm a bit nervous because this is my first interview.",
        "technical": "So, an API is basically a way for two programs to talk to each other. Like when you use the weather app on your phone, it uses an API to get the weather data from a server somewhere else."
    },
    {
        "name": "2. Genuine Senior Architect",
        "personal": "Good morning. I'm Sarah, I've been a software architect for about ten years now. My primary focus is on distributed systems and high-throughput data pipelines. Outside of work, I mentor junior developers.",
        "technical": "When designing a distributed system, you have to balance the CAP theorem tradeoffs. For our microservices, we typically chose eventual consistency over strong consistency to ensure high availability during network partitions, relying on event sourcing and CQRS."
    },
    {
        "name": "3. Highly Suspicious (Sudden Shift to AI Textbook)",
        "personal": "Hello sir, my name is Amit. I am learning computer. I want to get job here.",
        "technical": "A distributed database management system is a collection of logically interrelated databases distributed over a computer network. The fundamental challenge is maintaining ACID properties across geographically dispersed nodes while optimizing for availability and partition tolerance using the two-phase commit protocol."
    },
    {
        "name": "4. Needs Review (Rehearsed Human)",
        "personal": "Hey, I'm Jessica. I love designing user interfaces. I've been doing it for three years. I'm really excited for this role.",
        "technical": "User experience is... um, it encompasses all aspects of the end-user's interaction with the company, its services, and its products. The most important thing is meeting the exact needs of the customer, without fuss or bother. Then comes simplicity and elegance."
    },
    {
        "name": "5. Suspicious (AI Hedging and Structure)",
        "personal": "Hi, I'm David. I like coding in Python and doing data analysis. It's nice to meet you.",
        "technical": "It is important to note that Python's Global Interpreter Lock (GIL) prevents multiple native threads from executing Python bytecodes at once. Furthermore, when considering concurrency, one must evaluate whether the workload is I/O-bound or CPU-bound. In conclusion, multiprocessing is often preferred for CPU-bound tasks."
    },
    {
        "name": "6. Genuine Non-Native Speaker",
        "personal": "Hello, my name is Ling. I come from China. My English is not very perfect, but I try my best. I like doing front-end.",
        "technical": "For React, I use useEffect for fetching the data. If you don't put dependency array, it will render too many times and crash browser. So you must put empty array if you only want it run one time."
    },
    {
        "name": "7. Highly Suspicious (Massive Output Volume Difference)",
        "personal": "Hi I'm Mike.",
        "technical": "Cloud computing relies on three main service models: IaaS, PaaS, and SaaS. Infrastructure as a Service (IaaS) provides virtualized computing resources over the internet. Platform as a Service (PaaS) provides a platform allowing customers to develop, run, and manage applications without the complexity of building and maintaining the infrastructure. Software as a Service (SaaS) is a software distribution model in which a cloud provider hosts applications and makes them available to end users over the internet. These models offer scalability, flexibility, and cost-efficiency for modern enterprises."
    },
    {
        "name": "8. Suspicious (Inconsistent Register - Slang to Corporate)",
        "personal": "Yo what's up, I'm Kevin. Super stoked to be here man, I totally love building sick apps and just chilling with my dog.",
        "technical": "Synergistic cross-functional alignment is paramount when architecting scalable enterprise solutions. By leveraging robust agile methodologies, organizations can optimize their go-to-market strategies and ensure a paradigm shift in operational efficacy."
    },
    {
        "name": "9. Genuine Enthusiast",
        "personal": "Hi! I'm Elena, I'm completely obsessed with machine learning. I've been building random neural networks since I was 16. I just can't get enough of it!",
        "technical": "Okay so gradient descent is basically like trying to walk down a mountain blindfolded! You feel the slope with your feet, right? And you take a step in the steepest direction downward. The learning rate is just how big of a step you take. Too big and you jump over the valley, too small and it takes forever!"
    },
    {
        "name": "10. Highly Suspicious (Broken English to Complex Vocabulary)",
        "personal": "Hi, me is John. I like code.",
        "technical": "Polymorphism is an object-oriented programming concept that refers to the ability of a variable, function or object to take on multiple forms. It facilitates the implementation of elegant software design patterns and significantly augments code reusability and extensibility."
    }
]

def run_tests_and_generate_pdf():
    print("Running 10 test cases against the backend...")
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1 # Center
    
    case_title_style = styles['Heading2']
    case_title_style.textColor = HexColor('#2c3e50')
    
    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.leading = 14
    
    code_style = ParagraphStyle(
        'Code',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=9,
        leading=12,
        backColor=HexColor('#f4f6f7'),
        textColor=HexColor('#c0392b'),
        borderPadding=5
    )
    
    doc = SimpleDocTemplate("SachhAI_10_Test_Cases.pdf", pagesize=letter)
    story = []
    
    story.append(Paragraph("SachhAI - 10 Input Test Cases Report", title_style))
    story.append(Spacer(1, 20))
    
    for i, case in enumerate(TEST_CASES):
        print(f"Testing {case['name']}...")
        payload = {
            "candidate_id": f"test_candidate_{i+1}_{int(time.time())}",
            "personal": case["personal"],
            "technical": case["technical"]
        }
        
        try:
            resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=10)
            data = resp.json().get("analysis", {})
            
            verdict = data.get('verdict', 'UNKNOWN')
            score = data.get('authenticity_score', 0)
            flags = data.get('flags', [])
            
            # Format color based on verdict
            v_color = "#27ae60" if "GENUINE" in verdict else "#f39c12" if "REVIEW" in verdict else "#c0392b"
            
            story.append(Paragraph(case["name"], case_title_style))
            
            story.append(Paragraph("<b>Personal Input:</b>", normal_style))
            story.append(Paragraph(case["personal"], code_style))
            story.append(Spacer(1, 5))
            
            story.append(Paragraph("<b>Technical Input:</b>", normal_style))
            story.append(Paragraph(case["technical"], code_style))
            story.append(Spacer(1, 10))
            
            verdict_style = ParagraphStyle(
                'Verdict', parent=normal_style, textColor=HexColor(v_color), fontName='Helvetica-Bold'
            )
            story.append(Paragraph(f"Verdict: {verdict}", verdict_style))
            story.append(Paragraph(f"Authenticity Score: {score}/100", normal_style))
            
            if flags:
                story.append(Spacer(1, 5))
                story.append(Paragraph("<b>Flags Triggered:</b>", normal_style))
                for flag in flags:
                    story.append(Paragraph(f"• {flag}", normal_style))
            
            story.append(Spacer(1, 15))
            story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#bdc3c7')))
            story.append(Spacer(1, 15))
            
        except Exception as e:
            print(f"Error on {case['name']}: {e}")
            
    try:
        doc.build(story)
        print("\nPDF generated successfully: SachhAI_10_Test_Cases.pdf")
    except Exception as e:
        print(f"Error generating PDF: {e}")

if __name__ == "__main__":
    run_tests_and_generate_pdf()
