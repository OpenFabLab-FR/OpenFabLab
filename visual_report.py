"""An aggregate-only, in-memory presentation of the existing statistical results."""
import io
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,Rect,String,Line

BLUE='#2e718f';DARK='#1f5065';LIGHT='#edf4f6';MUTED='#566a73';BORDER='#d4e1e5'

def public_summary(statistics,structure):
    """Internal aggregate projection; historical function name kept for callers.

    No minimum cell size. Counts/percentages come from the existing statistical
    distributions, not individuals, raw sessions, contacts or private metadata.
    """
    summary=statistics['selected_summary'];services=statistics['service_statistics']
    result=dict(name=str(structure.get('name') or 'FabLab')[:160],period=statistics['selected_period_label'],
        coverage={k:statistics['coverage'][k] for k in ('message','period','timezone')},
        summary={k:summary[k] for k in ('sessions','visitors','unique_users','hours','open_lab_days')},
        services={k:services[k] for k in ('animations','animation_participants','animation_presence_incomplete')},
        days=[{k:day[k] for k in ('label','average_users','average_visitors','open_labs')} for day in statistics['busiest_weekdays']],
        hours=[dict(label=day['label'],days=day['open_labs'],bars=[{k:bar[k] for k in ('start','end','average_users','average_visitors')} for bar in day['bars']]) for day in statistics['openlab_attendance']['days'] if day['open_labs']],
        distributions=[])
    for title,key in [('Catégories','category_rows'),('Genres','gender_rows'),('Tranches d’âge','age_rows'),('Communes','city_export_rows'),('Nationalités','nationality_export_rows')]:
        source=statistics[key]
        total=sum(r['count'] for r in source)
        rows=[];unknown=[]
        for row in source:
            # Keep historical session/hour categories even if the period's
            # unique-user classification has moved to another category.
            if not row['count'] and not (key=='category_rows' and (row['sessions'] or row['hours'])):
                continue
            label=row.get('label')
            if not label or ('key' in row and row['key'] in ('unknown',None,'')):
                label='Non renseigné'
            item=dict(label=str(label),count=row['count'],percentage=row.get('percentage',
                round(row['count']/total*100,1) if total else 0))
            if key=='category_rows':item.update(sessions=row['sessions'],hours=row['hours'])
            if key in ('city_export_rows','nationality_export_rows') and label=='Non renseigné':
                unknown.append(item)
            else:rows.append(item)
        if key in ('city_export_rows','nationality_export_rows'):
            # Presentation only: 20 named values, not the screen's top-10.
            # Missing information stays explicit and uses the same denominator.
            rows.sort(key=lambda r:(-r['count'],r['label'].casefold(),r['label']))
            remainder=rows[20:];rows=rows[:20]
            if remainder:
                count=sum(r['count'] for r in remainder)
                rows.append(dict(label='Autres',count=count,percentage=round(count/total*100,1) if total else 0))
            rows.extend(unknown)
        result['distributions'].append(dict(title=title,available=bool(rows),total=total,rows=rows))
    return result

def _fonts():
    base=Path(__file__).parent/'static/fonts'
    for name,file in [('OFLRegular','LibreFranklin-Regular.ttf'),('OFLBold','LibreFranklin-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(base/file)))
    pdfmetrics.registerFontFamily('OFLRegular',normal='OFLRegular',bold='OFLBold',italic='OFLRegular',boldItalic='OFLBold')

def _bars(rows,label_key,value_key,width=176*mm):
    height=max(56,len(rows)*26+14);drawing=Drawing(width,height)
    peak=max((r[value_key] for r in rows),default=1) or 1
    left=72*mm;available=width-left-20*mm
    for index,row in enumerate(rows):
        y=height-24-index*26;label=str(row[label_key]);size=9
        while label and pdfmetrics.stringWidth(label,'OFLRegular',size)>left-10:label=label[:-1]
        if label!=str(row[label_key]):label=label.rstrip()+'…'
        drawing.add(String(0,y+3,label,fontName='OFLRegular',fontSize=size,fillColor=colors.HexColor(DARK)))
        drawing.add(Rect(left,y,available,14,fillColor=colors.HexColor(LIGHT),strokeColor=None))
        drawing.add(Rect(left,y,available*row[value_key]/peak,14,fillColor=colors.HexColor(BLUE),strokeColor=None))
        drawing.add(String(left+available+7,y+3,str(row[value_key]).replace('.',','),fontName='OFLBold',fontSize=9,fillColor=colors.HexColor(DARK)))
    return drawing

def _hour_chart(day,width=176*mm):
    height=100;chart=Drawing(width,height);bars=day['bars'];peak=max((b['average_users'] for b in bars),default=0);scale=peak or 1
    chart.add(Line(0,25,width,25,strokeColor=colors.HexColor(BORDER)))
    step=width/max(1,len(bars))
    for i,bar in enumerate(bars):
        chart.add(Rect(i*step,25,max(1,step-2),58*bar['average_users']/scale,fillColor=colors.HexColor(BLUE),strokeColor=None))
        every=max(1,(len(bars)+7)//8)
        if i%every==0:chart.add(String(i*step,10,bar['start'],fontName='OFLRegular',fontSize=7,fillColor=colors.HexColor(MUTED)))
    chart.add(String(0,90,'Maximum : '+str(peak).replace('.',',')+(' usager' if peak==1 else ' usagers')+' en moyenne / quart d’heure',fontName='OFLRegular',fontSize=8,fillColor=colors.HexColor(MUTED)))
    return chart

def _distribution_table(dimension,p,width):
    """Paginated bars + exact figures; full labels wrap instead of truncating.

    repeatRows keeps labels/units on following pages. No small-cell hiding.
    Use a single scale for the entire displayed dimension across pages.
    """
    rows=[[p(dimension['title'],'h1'),'','',''],
          [p('Libellé','small'),p('Échelle relative','small'),p('Effectif','small'),p('Part','small')]]
    bar_width=width*.24-16
    peak=max((r['count'] for r in dimension['rows']),default=0) or 1
    for row in dimension['rows']:
        bar=Drawing(bar_width,11)
        bar.add(Rect(0,1,bar_width,9,fillColor=colors.HexColor(LIGHT),strokeColor=None))
        if row['count']:
            bar.add(Rect(0,1,bar_width*row['count']/peak,9,fillColor=colors.HexColor(BLUE),strokeColor=None))
        percentage=f"{row['percentage']:.1f}".replace('.',',')+' %'
        rows.append([p(row['label'],'small'),bar,p(row['count'],'number'),p(percentage,'number')])
    rows.append([p('Total','small'),'',p(dimension['total'],'number'),p('100,0 %' if dimension['total'] else '-','number')])
    table=Table(rows,colWidths=[width*.48,width*.24,width*.12,width*.16],repeatRows=2,hAlign='LEFT',style=TableStyle([
        ('SPAN',(0,0),(-1,0)),('LEFTPADDING',(0,0),(-1,0),0),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BACKGROUND',(0,1),(-1,1),colors.HexColor(LIGHT)),
        ('LINEBELOW',(0,1),(-1,1),.5,colors.HexColor(BORDER)),('LINEABOVE',(0,-1),(-1,-1),.5,colors.HexColor(BORDER)),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    return KeepTogether([table]) if len(dimension['rows'])<=8 else table

def generate_visual_report(statistics,structure):
    data=public_summary(statistics,structure);_fonts();stream=io.BytesIO();width=176*mm
    styles={k:ParagraphStyle(k,fontName='OFLRegular',fontSize=size,leading=leading,textColor=colors.HexColor(color),spaceAfter=space)
        for k,size,leading,color,space in [('title',25,31,DARK,12),('h1',15,20,DARK,10),('h2',11,15,BLUE,7),('body',9,13,DARK,8),('small',8,11,MUTED,7)]}
    styles['h1'].keepWithNext=True;styles['h2'].keepWithNext=True
    styles['number']=ParagraphStyle('number',parent=styles['small'],alignment=2)
    p=lambda text,style='body':Paragraph(escape(str(text)),styles[style])
    story=[p(data['name'],'h2'),p('Bilan visuel de fréquentation','title'),p('Période : '+str(data['period']),'h1'),
        p(data['coverage']['message']),p(data['coverage']['period'],'small')]
    metrics=[('Passages identifiés',data['summary']['sessions']),('Visiteurs anonymes',data['summary']['visitors']),
        ('Usagers distincts',data['summary']['unique_users']),('Heures - sessions terminées',str(data['summary']['hours']).replace('.',',')),
        ('Jours avec passages identifiés',data['summary']['open_lab_days']),('Animations passées',data['services']['animations'])]
    cells=[Paragraph(f'<font name="OFLBold" size="23" color="{BLUE}">{value}</font><br/><font size="9">{escape(label)}</font>',ParagraphStyle('metric',parent=styles['body'],leading=20)) for label,value in metrics]
    table=Table([cells[:3],cells[3:]],colWidths=[width/3]*3)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor(LIGHT)),('BOX',(0,0),(-1,-1),.5,colors.HexColor(BORDER)),('INNERGRID',(0,0),(-1,-1),.5,colors.HexColor(BORDER)),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),16),('BOTTOMPADDING',(0,0),(-1,-1),14)]))
    story+=[table,Spacer(1,7*mm),p('Animations et participation','h1'),p(f"{data['services']['animation_participants']} participations renseignées aux animations passées.")]
    story+=[p('Une animation passée selon sa date ne prouve pas sa tenue. Les réservations futures ne sont pas comptées comme des présences.','small')]
    if data['services']['animation_presence_incomplete']:story+=[p(f"Présences incomplètes ou non renseignées pour {data['services']['animation_presence_incomplete']} animation(s) passée(s) ; total non exhaustif.",'small')]
    if data['days']:
        story+=[p('Jours les plus fréquentés','h1'),p('Usagers distincts en moyenne par journée avec passages identifiés ; pas un décompte des ouvertures organisées.','small'),_bars(data['days'],'label','average_users',width)]
    if data['hours']:
        story+=[PageBreak(),p('Habitudes de fréquentation','title'),p('Présence moyenne par quart d’heure','h1'),p('Sessions terminées, sur les journées avec passages identifiés et les horaires configurés. Les visiteurs anonymes sont des arrivées, sans durée de présence mesurée.','small')]
        for day in data['hours']:
            label=day['label']+f" - {day['days']} "+('jour observé' if day['days']==1 else 'jours observés')
            chart=_hour_chart(day,width) if any(b['average_users'] for b in day['bars']) else p('Aucune présence terminée mesurée sur la plage horaire configurée.','small')
            story.append(KeepTogether([p(label,'h2'),chart,Spacer(1,3*mm)]))
    if data['summary']['unique_users'] and any(d['available'] for d in data['distributions']):
        story+=[PageBreak(),p('Les publics, en synthèse','title'),p('Bilan interne : répartitions agrégées, sans croisement de données individuelles. Les petits effectifs sont affichés ; examiner le document avant tout partage extérieur.','small'),
            p('Pourcentages calculés sur le total de chaque répartition, « Non renseigné » compris. Les arrondis à une décimale peuvent donner une somme légèrement différente de 100 %. Barres comparées au plus grand effectif de la répartition.','small'),
            p('Communes et nationalités : les 20 valeurs renseignées les plus représentées sont détaillées, le reste est regroupé dans « Autres ». Les données absentes restent dans « Non renseigné ».','small')]
        for dimension in data['distributions']:
            if not dimension['available']:story+=[p(dimension['title'],'h1'),p('Aucune donnée pour cette répartition.','small')];continue
            story.append(_distribution_table(dimension,p,width))
            if dimension['title']=='Catégories':
                story.append(p('Usagers distincts : catégorie retenue par les statistiques pour la période. Sessions et heures : catégorie enregistrée à chaque passage.','small'))
                rows=[[p('Catégorie','small'),p('Sessions','small'),p('Heures terminées','small')]]
                rows += [[p(r['label'],'small'),p(r['sessions'],'small'),p(str(r['hours']).replace('.',','),'small')] for r in dimension['rows']]
                story.append(Table(rows,colWidths=[width*.56,width*.18,width*.26],repeatRows=1,style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor(BORDER))])))
    elif data['summary']['unique_users']:story+=[p('Aucune répartition de publics disponible pour cette période.','small')]
    else:story+=[p('Aucune donnée de fréquentation pour cette période. Aucun profil de public n’est déduit.','h2')]
    def footer(canvas,document):
        canvas.saveState();canvas.setFont('OFLRegular',7);canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(17*mm,10*mm,'OpenFabLab - statistiques agrégées - '+data['coverage']['timezone'])
        canvas.drawRightString(A4[0]-17*mm,10*mm,f'Page {document.page}');canvas.restoreState()
    doc=SimpleDocTemplate(stream,pagesize=A4,leftMargin=17*mm,rightMargin=17*mm,topMargin=17*mm,bottomMargin=19*mm,title='Bilan visuel de fréquentation',author='OpenFabLab')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()
