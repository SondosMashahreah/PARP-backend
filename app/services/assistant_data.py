"""Read-only, server-authorized tools. No model-provided role or SQL is accepted."""
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, func, or_, false
from app.domain.roles import normalize_role
from app.domain.errors import ApplicationError
from app.models.user import User
from app.models.education import School, Directorate
from app.models.workflow import ResearchSubmission as Research, UserAffiliation, ReviewAssignment, ResearchReview, ProblemRecord, RecommendationRecord
from app.models.platform import Conference, ConferenceParticipation, CommitteeAccount, PublicationPayment, PlatformNotice
from app.models.researcher import ResearchDraft, TrainingProgress, ResearcherCertificate
from app.models.excellence import ExcellenceEntry
from app.models.news import NewsArticle
from app.services.platform import scope as participation_scope
from app.schemas.assistant import ReadRequest

LIMIT = 20
SHARED = ['/', '/about', '/news', '/search', '/profile', '/support', '/repository', '/excellence', '/practices', '/assistant']
ROLE_PAGES = {
    'guest': ['/', '/about', '/repository', '/excellence', '/practices', '/assistant', '/guide', '/template', '/training', '/library', '/conference', '/news', '/support'],
    'researcher': ['/workspace','/conference','/guide','/template','/training','/library','/news','/problems'],
    'reviewer': ['/workspace','/guide','/library'],
    'school_manager': ['/workspace','/institutions'],
    'directorate_manager': ['/workspace','/institutions','/map','/training'],
    'scientific_committee': ['/workspace','/guide','/template','/conference'],
    'organizing_committee': ['/workspace','/conference','/news'],
    'decision_maker': ['/workspace','/problems','/observatory','/map','/institutions'],
    'system_admin': ['/workspace','/dashboard'],
}

def role(user):
    return normalize_role(user.role) if user else 'guest'

def allowed_pages(user):
    return list(dict.fromkeys(SHARED + ROLE_PAGES.get(role(user), [])))

def approved_affiliation(db, user):
    if not user or isinstance(user, CommitteeAccount):
        return None
    aff = db.get(UserAffiliation, user.id)
    return aff if aff and aff.approval_status == 'approved' else None

def scope_label(user):
    return {'school_manager':'school','directorate_manager':'directorate','researcher':'own','reviewer':'assigned','organizing_committee':'assigned_conference','system_admin':'platform_admin','decision_maker':'platform_statistics','scientific_committee':'scientific_committee'}.get(role(user),'public')

def scoped_research(db, user, public=True):
    stmt = select(Research)
    if public:
        return stmt.where(Research.status == 'published')
    r = role(user)
    if r == 'researcher':
        return stmt.where(Research.researcher_id == user.id)
    if r == 'reviewer':
        return stmt.where(Research.id.in_(select(ReviewAssignment.submission_id).where(ReviewAssignment.reviewer_id == user.id)))
    if r in ('system_admin','decision_maker','scientific_committee'):
        return stmt
    aff = approved_affiliation(db, user)
    if aff and r == 'school_manager' and aff.school_id:
        return stmt.where(Research.school_id == aff.school_id)
    if aff and r == 'directorate_manager' and aff.directorate_id:
        return stmt.where(Research.directorate_id == aff.directorate_id)
    return stmt.where(false())

def registered_schools(db, user):
    # School is a reference catalog, not a platform-registration table.
    registered = select(UserAffiliation.school_id).join(User, User.id == UserAffiliation.user_id).where(
        UserAffiliation.approval_status == 'approved', UserAffiliation.school_id.is_not(None),
        User.is_active.is_(True), User.role.in_(['researcher','user','school_manager']))
    stmt = select(School).where(School.id.in_(registered))
    r, aff = role(user), approved_affiliation(db,user)
    if r == 'school_manager':
        stmt = stmt.where(School.id == aff.school_id) if aff and aff.school_id else stmt.where(false())
    if r == 'directorate_manager':
        stmt = stmt.where(School.directorate_id == aff.directorate_id) if aff and aff.directorate_id else stmt.where(false())
    return stmt

def count(db, stmt):
    return int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)

def summary(db, user):
    public = scoped_research(db,user)
    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'scope':scope_label(user),
        'registered_schools':count(db,registered_schools(db,user)),
        'registered_schools_definition':'Distinct schools with at least one active researcher/teacher or school-manager account with approved affiliation. NOT the imported school/map catalog. School/directorate managers only count their authorized scope.',
        'public_platform':{'published_news':count(db,select(NewsArticle).where(NewsArticle.published.is_(True))),
                           'published_research':count(db,public.where(Research.publication_type=='research')),
                           'published_practices':count(db,public.where(Research.publication_type=='practice')),
                           'published_authors':count(db,select(Research.researcher_id).where(Research.status=='published').distinct()),
                           'visible_excellence_cards':count(db,excellence_query()),
                           'excellence_people':count(db,excellence_query().with_only_columns(Research.researcher_id).distinct())},
        'allowed_pages':allowed_pages(user),
    }
    if role(user) not in ('guest','organizing_committee'):
        base=scoped_research(db,user,False).subquery()
        result['workspace_statuses']={str(status):int(n) for status,n in db.execute(select(base.c.status,func.count()).group_by(base.c.status))}
    if role(user) == 'system_admin':
        result['registered_accounts']=int(db.scalar(select(func.count()).select_from(User)) or 0)
    if role(user) == 'system_admin':
        result['account_roles']={str(r):int(n) for r,n in db.execute(select(User.role,func.count()).group_by(User.role))}
        result['pending_affiliations']=int(db.scalar(select(func.count()).select_from(UserAffiliation).where(UserAffiliation.approval_status=='requested')) or 0)
    if role(user) in ('decision_maker','directorate_manager'):
        catalog=select(School)
        if role(user)=='directorate_manager':
            aff=approved_affiliation(db,user)
            catalog=catalog.where(School.directorate_id==aff.directorate_id) if aff and aff.directorate_id else catalog.where(false())
        result['reference_map_schools_NOT_registered']=count(db,catalog)
    return result

def excellence_query():
    return select(ExcellenceEntry).join(Research,Research.id==ExcellenceEntry.submission_id).where(
        ExcellenceEntry.visible.is_(True),ExcellenceEntry.image_object.is_not(None),Research.status=='published',func.length(func.trim(Research.abstract))>0)

def search(stmt, q, *columns):
    if not q.strip(): return stmt
    pattern='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    return stmt.where(or_(*[c.ilike(pattern,escape='\\') for c in columns]))

def page(db, stmt, offset, serialize):
    total=count(db,stmt)
    rows=db.scalars(stmt.offset(offset).limit(LIMIT)).all()
    return {'items':[serialize(r) for r in rows], 'total':total, 'offset':offset, 'limit':LIMIT, 'has_more':offset+len(rows)<total}

def public_person_ids():
    return select(Research.researcher_id).where(Research.status=='published').distinct()

def people_query(db,user,public):
    stmt=select(User)
    if public: return stmt.where(User.id.in_(public_person_ids()))
    if role(user)=='system_admin':return stmt
    if role(user)=='researcher':return stmt.where(User.id==user.id)
    aff=approved_affiliation(db,user)
    if aff and role(user) in ('school_manager','directorate_manager'):
        condition=UserAffiliation.school_id==aff.school_id if role(user)=='school_manager' and aff.school_id else UserAffiliation.directorate_id==aff.directorate_id if role(user)=='directorate_manager' and aff.directorate_id else false()
        return stmt.where(User.id.in_(select(UserAffiliation.user_id).where(condition,UserAffiliation.approval_status=='approved')))
    return stmt.where(false())

def person(db, row):
    aff=db.get(UserAffiliation,row.id)
    aff=aff if aff and aff.approval_status=='approved' else None
    school=db.get(School,aff.school_id) if aff and aff.school_id else None
    directorate=db.get(Directorate,aff.directorate_id) if aff and aff.directorate_id else None
    return {'id':row.id,'name':row.full_name,'school':school.name_ar if school else None,'school_en':school.name_en if school else None,
        'directorate':directorate.name_ar if directorate else None,'specialization':aff.specialization if aff else None,
        'published_research':count(db,select(Research).where(Research.researcher_id==row.id,Research.status=='published',Research.publication_type=='research'))}

def research_item(db,user,row,detail=False):
    author=db.get(User,row.researcher_id)
    data={'id':row.id,'title':row.title,'title_en':row.title_en,'researcher_id':row.researcher_id,'researcher_name':author.full_name if author else None,
          'status':row.status,'publication_type':row.publication_type,'research_field':row.research_field,'published_at':row.published_at.isoformat() if row.published_at else None,'abstract':(row.abstract or '')[:16000 if detail else 1200]}
    if detail:
        assigned=role(user)=='reviewer' and db.scalar(select(ReviewAssignment.id).where(ReviewAssignment.submission_id==row.id,ReviewAssignment.reviewer_id==user.id,ReviewAssignment.confidentiality_accepted.is_(True)))
        private=bool(user and not isinstance(user,CommitteeAccount) and (user.id==row.researcher_id or role(user)=='system_admin' or assigned))
        if private or row.status=='published' and row.publication_type=='practice':
            for field in ('problem','research_question','intervention','results','recommendations','keywords'):
                data[field]=getattr(row,field)
        data['content_access']='research_form_fields' if private else 'public_practice' if row.publication_type=='practice' and row.status=='published' else 'abstract_only'
        data['uploaded_document_read']=False
        if private and (user.id==row.researcher_id or assigned):
            reviews=select(ResearchReview).where(ResearchReview.submission_id==row.id)
            if assigned and user.id!=row.researcher_id:reviews=reviews.where(ResearchReview.reviewer_id==user.id)
            data['reviews']=[{'recommendation':r.recommendation,'comments':r.comments,'rubric':r.rubric} for r in db.scalars(reviews.limit(20))]
    return data

def read_platform(db,user,args):
    a=ReadRequest.model_validate(args); ds=a.dataset
    if ds=='news':
        from app.services import news
        private = a.visibility == 'workspace' and role(user) == 'system_admin'
        if a.record_id:
            if not a.record_id.isdigit():
                return {'unavailable': 'Invalid news id'}, '/news'
            row = news.get_article(db, int(a.record_id), public=not private)
            return news.serialize(row, full=True, private=private), f'/news?article={row.id}'
        return news.list_articles(db, public=not private, q=a.q or '', offset=a.offset), '/news'
    if ds=='summary':return summary(db,user),'/assistant'
    if ds=='knowledge':
        docs=json.loads((Path(__file__).parents[1]/'data/assistant_knowledge.json').read_text())
        # Guidance is shared; private page instructions remain filtered.
        docs=[d for d in docs if d.get('guidance') or d['path'] in allowed_pages(user)]
        if a.q:docs=[d for d in docs if a.q.casefold() in json.dumps(d,ensure_ascii=False).casefold()]
        return {'items':docs,'note':'Versioned platform guidance; illustrative examples are not live records.'},'/assistant'
    if ds=='affiliations':
        stmt=select(UserAffiliation).join(User,User.id==UserAffiliation.user_id)
        r,aff=role(user),approved_affiliation(db,user)
        if r=='system_admin':pass
        elif r=='school_manager' and aff and aff.school_id:stmt=stmt.where(UserAffiliation.school_id==aff.school_id)
        elif r=='directorate_manager' and aff and aff.directorate_id:stmt=stmt.where(UserAffiliation.directorate_id==aff.directorate_id)
        elif r=='researcher':stmt=stmt.where(UserAffiliation.user_id==user.id)
        else:return {'unavailable':'Affiliation records are not accessible to this role.'},'/assistant'
        if a.status:stmt=stmt.where(UserAffiliation.approval_status==a.status)
        if a.record_id:stmt=stmt.where(UserAffiliation.user_id==a.record_id)
        stmt=search(stmt,a.q,User.full_name)
        return page(db,stmt.order_by(UserAffiliation.user_id),a.offset,lambda v:{'user_id':v.user_id,'name':db.get(User,v.user_id).full_name,'school_id':v.school_id,'directorate_id':v.directorate_id,'approval_status':v.approval_status}),'/workspace'
    if ds=='assignments':
        stmt=select(ReviewAssignment)
        if role(user)=='reviewer':stmt=stmt.where(ReviewAssignment.reviewer_id==user.id)
        elif role(user)!='system_admin':return {'unavailable':'Review assignments are not accessible to this role.'},'/assistant'
        if a.status:stmt=stmt.where(ReviewAssignment.status==a.status)
        if a.record_id:stmt=stmt.where(ReviewAssignment.id==a.record_id)
        return page(db,stmt.order_by(ReviewAssignment.id.desc()),a.offset,lambda v:{'id':v.id,'submission_id':v.submission_id,'reviewer_id':v.reviewer_id,'status':v.status,'confidentiality_accepted':v.confidentiality_accepted}),'/workspace'
    if ds=='schools':
        stmt=search(registered_schools(db,user),a.q,School.name_ar,School.name_en)
        if a.record_id:stmt=stmt.where(School.id==a.record_id)
        return page(db,stmt.order_by(School.name_ar),a.offset,lambda r:{'id':r.id,'name_ar':r.name_ar,'name_en':r.name_en,'directorate_id':r.directorate_id}),'/institutions' if '/institutions' in allowed_pages(user) else '/assistant'
    if ds=='people':
        stmt=search(people_query(db,user,a.visibility=='public'),a.q,User.full_name)
        if a.record_id:stmt=stmt.where(User.id==a.record_id)
        return page(db,stmt.order_by(User.id),a.offset,lambda r:person(db,r)),'/repository' if a.visibility=='public' else '/workspace'
    if ds=='research':
        stmt=scoped_research(db,user,a.visibility=='public')
        stmt=search(stmt,a.q,Research.title,Research.title_en,Research.research_field)
        if a.record_id:stmt=stmt.where(Research.id==a.record_id)
        if a.author_id:stmt=stmt.where(Research.researcher_id==a.author_id)
        if a.status:stmt=stmt.where(Research.status==a.status)
        if a.kind:stmt=stmt.where(Research.publication_type==a.kind)
        return page(db,stmt.order_by(Research.id.desc()),a.offset,lambda r:research_item(db,user,r,bool(a.record_id))),'/repository' if a.visibility=='public' else '/workspace'
    if ds=='excellence':
        stmt=search(excellence_query(),a.q,ExcellenceEntry.name_ar,ExcellenceEntry.name_en,Research.title)
        if a.record_id:stmt=stmt.where(ExcellenceEntry.id==a.record_id)
        def card(r):
            research=db.get(Research,r.submission_id);c=db.get(Conference,r.conference_id)
            return {'id':r.id,'name_ar':r.name_ar,'name_en':r.name_en,'researcher_id':research.researcher_id,'research_title':research.title,'conference':c.title,'year':c.starts_at.year,'profile_url':f'/excellence?researcher={r.id}'}
        return page(db,stmt.order_by(ExcellenceEntry.id),a.offset,card),'/excellence'
    if ds=='conferences':
        if '/conference' not in allowed_pages(user):return {'unavailable':'Conference page is not available to this role.'},'/assistant'
        stmt=search(select(Conference),a.q,Conference.title)
        if role(user)=='organizing_committee':stmt=stmt.where(Conference.id==getattr(user,'conference_id',None))
        if a.record_id:stmt=stmt.where(Conference.id==a.record_id)
        return page(db,stmt.order_by(Conference.starts_at.desc()),a.offset,lambda r:{'id':r.id,'title':r.title,'venue':r.venue,'starts_at':r.starts_at.isoformat(),'ends_at':r.ends_at.isoformat(),'deadline':r.deadline.isoformat()}),'/conference'
    if ds=='participations':
        if not user:return {'unavailable':'Sign in required'},'/assistant'
        stmt=participation_scope(db,user,select(ConferenceParticipation),ConferenceParticipation)
        stmt=search(stmt,a.q,ConferenceParticipation.title)
        if a.record_id:stmt=stmt.where(ConferenceParticipation.id==a.record_id)
        return page(db,stmt.order_by(ConferenceParticipation.id.desc()),a.offset,lambda r:{'id':r.id,'title':r.title,'abstract':r.abstract,'status':r.status,'conference_id':r.conference_id,'researcher_id':r.researcher_id,'notes':r.notes}),'/workspace'
    if ds in ('drafts','training','certificates'):
        if role(user)!='researcher':return {'unavailable':'Only the researcher may read their own workspace records.'},'/assistant'
        model={'drafts':ResearchDraft,'training':TrainingProgress,'certificates':ResearcherCertificate}[ds]
        owner=model.researcher_id if ds=='drafts' else model.user_id
        stmt=select(model).where(owner==user.id)
        if a.record_id:stmt=stmt.where(model.id==a.record_id)
        def own(r):
            if ds=='drafts':return {'id':r.id,'content':r.content if a.record_id else {'title':r.content.get('title')},'revision':r.revision}
            if ds=='training':return {'id':r.id,'title':r.title,'completed':r.completed,'total':r.total}
            return {'id':r.id,'title':r.title,'issuer':r.issuer,'issued_at':r.issued_at.isoformat()}
        return page(db,stmt.order_by(model.id),a.offset,own),'/workspace'
    if ds=='payments':
        if role(user) not in ('system_admin','researcher'):return {'unavailable':'Payment details are not available to this role.'},'/assistant'
        stmt=select(PublicationPayment)
        if role(user)=='researcher':stmt=stmt.where(PublicationPayment.submission_id.in_(select(Research.id).where(Research.researcher_id==user.id)))
        if a.record_id:stmt=stmt.where(PublicationPayment.submission_id==a.record_id)
        return page(db,stmt.order_by(PublicationPayment.submission_id),a.offset,lambda r:{'submission_id':r.submission_id,'required_agorot':r.required_agorot,'paid_agorot':r.paid_agorot,'confirmed':r.confirmed}),'/dashboard' if role(user)=='system_admin' else '/workspace'
    if ds=='notices':
        if not user or isinstance(user,CommitteeAccount):return {'items':[],'total':0},'/assistant'
        stmt=select(PlatformNotice).where(PlatformNotice.user_id==user.id)
        return page(db,stmt.order_by(PlatformNotice.id.desc()),a.offset,lambda r:{'text':r.text,'created_at':r.created_at.isoformat()}),'/workspace'
    if ds in ('problems','recommendations'):
        required='/problems' if ds=='problems' else '/observatory'
        if required not in allowed_pages(user):return {'unavailable':'Not available to this role'},'/assistant'
        model=ProblemRecord if ds=='problems' else RecommendationRecord
        stmt=select(model).where(model.submission_id.in_(select(Research.id).where(Research.status=='published')))
        stmt=search(stmt,a.q,model.text,model.research_field)
        return page(db,stmt.order_by(model.id.desc()),a.offset,lambda r:{'id':r.id,'text':r.text,'research_field':r.research_field}),required
    raise ApplicationError(422,'Unsupported data source')
