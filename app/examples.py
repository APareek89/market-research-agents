"""Three authored examples, executed through the real council with prepared replies."""
import asyncio
from langchain_core.messages import AIMessage
from .execution import current_execution

EXAMPLES={
 'market-entry':{'title':'Size an AI editing opportunity','description':'An illustrative market-entry decision with explicit assumptions.','prompt':'Should a small team test an AI image-editing service for Indian ecommerce sellers?',
 'brief':'Assess a narrow ecommerce editing workflow in India. Use illustrative pilot assumptions, not invented market statistics. Recommend the next validation decision.',
 'report':'''## AI image editing: validate a narrow workflow first

**Prepared example — no live research or model call. All quantities are illustrative assumptions.**

Recommend a four-week pilot with ten ecommerce teams handling recurring product-image batches. A national business count is not an addressable-market estimate: reachable customers must have frequent editing work, authority to buy, and willingness to change their process.

| Pilot assumption | Illustrative input | Evidence to collect |
|---|---:|---|
| Participating teams | 10 | Confirm repeat weekly use |
| Editing time per team | 5 hours/week | Time identical before/after batches |
| Target time saving | 50% | Include human quality-review time |

At these assumptions, the pilot saves 25 hours each week across ten teams. This is a workflow calculation, not a revenue forecast. Price tests should compare the avoided cost with a real paid offer.

### Decision and risks
Continue only if teams repeat usage, accept output quality and commit to a paid plan. Segment by workflow volume before expanding. Privacy, inconsistent images and manual review can erase the apparent saving.

### Next evidence
Interview the workflow owner, record current costs, measure a comparable image batch and test willingness to pay. Report missing evidence instead of presenting a speculative market size.''',
 'review':'The national market is not yet measured. Separate reachable users from all businesses, include review time in savings and require a paid-offer test.',
 'client':'A buyer needs predictable quality and a reversible pilot. Name the workflow owner and make repeat weekly usage a continuation condition.'},
 'pricing-comparison':{'title':'Compare competitor pricing','description':'Compare three fictional plans using an included, clearly illustrative dataset.','prompt':'Compare fictional editing plans: Basic $20 for 100 images, Growth $60 for 500 images, Team $150 for 1500 images. What should a 400-image/month team test?',
 'brief':'Compare the supplied fictional monthly prices and image allowances for a 400-image workflow. Do not invent overage rates or vendor claims.',
 'report':'''## Pricing comparison for a 400-image workflow

**Prepared example — fictional plans supplied for illustration; no live vendor research or model call.**

| Plan | Monthly price | Included images | Price per included image |
|---|---:|---:|---:|
| Basic | $20 | 100 | $0.20 |
| Growth | $60 | 500 | $0.12 |
| Team | $150 | 1,500 | $0.10 |

Growth is the smallest listed plan that covers 400 images. Its effective cost at that usage is $0.15 per image. Team has a lower fully-utilized unit price but costs $90 more monthly and leaves most allowance unused. Basic overage policy is unknown; four subscriptions cannot be assumed valid.

### Recommendation
Trial Growth against a representative image batch before purchasing. Verify output quality, commercial rights, failed-job billing, team seats, rollover and cancellation terms. These unknowns can outweigh the headline unit price.

### Decision gate
Buy only after confirming the 400-image workload, acceptable results and final contract terms. Recalculate when observed usage changes; do not optimize for unused capacity.''',
 'review':'Use actual utilization as well as headline unit price. No overage or multi-account workaround can be assumed from the supplied data.',
 'client':'Confirm quality and contract rights in a trial. The smallest adequate plan is preferable to paying for unused volume.'},
 'product-validation':{'title':'Evaluate a watermark-removal idea','description':'Assess demand, rights and a bounded product validation pilot.','prompt':'How should a team validate a video watermark-removal feature for customers editing videos they own or are authorized to modify?',
 'brief':'Evaluate an authorized-media editing use case. Separate demand evidence, technical quality and content rights. Propose a small pilot without claiming market demand is proven.',
 'report':'''## Validate the authorized-video workflow before expanding

**Prepared example — a research plan, not a claim of proven demand. No live research or model call.**

Start with teams re-editing videos they own or have permission to modify. Screen for rights and retain an explicit consent step. A broad removal claim could attract misuse and unsuitable expectations.

### Pilot design
Recruit a small cohort with repeated legitimate cleanup needs. Use consented clips spanning movement, texture and overlay placement; compare artifacts, turnaround time and human review against the current process. Record failures as well as successful samples.

### Commercial evidence
Ask for a real paid pilot rather than a hypothetical willingness-to-pay answer. Measure repeat use, support burden and cost per accepted output. Treat these as hypotheses until observed.

### Continue, narrow or stop
Continue only if authorized repeat demand, acceptable quality and sustainable unit economics coincide. Narrow the supported footage if artifacts cluster in difficult cases. Stop if demand is mainly unauthorized removal or review effort erases the benefit.''',
 'review':'Test accepted-output cost and failure distribution, not just attractive demonstrations. Demand and technical capability are separate hypotheses.',
 'client':'Clarify supported footage and rights requirements before a paid pilot; provide an honest failure policy.'}
}

def listing():
    return [{'id':key,**{k:value[k] for k in ('title','description','prompt')}} for key,value in EXAMPLES.items()]

def config():
    return {'enable_reviewer':True,'enable_client':True,'custom_agents':[],'stage_order':['reviewer','client'],'settings':{},'agents':{}}

class FixtureModel:
    def __init__(self,role,structured=None):
        self.role=role
        self.structured=structured
    def bind_tools(self,tools):
        return self
    def with_structured_output(self,schema,**kwargs):
        return FixtureModel(self.role,schema)
    async def ainvoke(self,messages):
        scope=current_execution()
        if scope.mode not in {'cached','mock'}:
            raise RuntimeError('Prepared output cannot run in a live context')
        await asyncio.sleep(0.02)
        if self.structured:
            return {'lenses':[],'no_fit':True} if self.role=='router' else {'plans':[]}
        example=EXAMPLES.get(scope.example_id)
        if example is None:
            # A local mock is visibly synthetic and is never described as research.
            content=('Synthetic test brief; no provider call.' if self.role=='intake' else '## Synthetic test output\n\nLocal mock mode is enabled. No live research or provider request was made.')
        elif self.role=='intake':content=example['brief']+'\n\nPrepared example intake; no provider call.'
        elif self.role=='reviewer':content=example['review']+'\n\nPrepared reviewer response.'
        elif self.role=='client':content=example['client']+'\n\nPrepared client response.'
        else:content=example['report']
        return AIMessage(content=content,usage_metadata={'input_tokens':0,'output_tokens':0,'total_tokens':0})
