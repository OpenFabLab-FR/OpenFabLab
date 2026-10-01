<?php
// Private administration and all sending paths, fictional PDO fixtures; no network or real mail.
function is_user_logged_in(){return $GLOBALS['email_logged']??true;}
function current_user_can($cap){return $GLOBALS['email_admin']??true;}
function get_current_user_id(){return 7;}
function wp_verify_nonce($v,$a){return$v==='fixture-email-nonce'&&$a==='openfablab_res_email_templates';}
function wp_nonce_field($a){echo '<input type="hidden" name="_wpnonce" value="fixture-email-nonce">';}
function esc_html($v){return htmlspecialchars((string)$v,ENT_QUOTES,'UTF-8');}
function esc_attr($v){return esc_html($v);}
function get_transient($key){return$GLOBALS['email_transients'][$key]??false;}
function set_transient($key,$value,$duration){$GLOBALS['email_transients'][$key]=$value;}
ob_start();require __DIR__.'/test_wordpress_slots.php';ob_end_clean();
$tests=0;$wpdb=new SlotDatabase();$mails=[];$email_test_options=[];$email_transients=[];
$_SERVER['REQUEST_METHOD']='POST';
function email_action($action,$extra=[]){
    return OpenFabLab_Emails::handle_request($extra+['openfablab_email_action'=>$action,'_wpnonce'=>'fixture-email-nonce','email_model'=>'confirmation',
        'subject'=>'Bonjour {{participant_name}}','body'=>"ID : {{public_id_or_not_provided}}\n{{slot_details}}\n{{cancel_url}}\n{{signature}}"]);
}
function email_error($action,$extra=[]){return isset(email_action($action,$extra)['error']);}

if(($argv[1]??'')==='html'){
    $mode=$argv[2]??'settings';
    if($mode==='denied')$email_admin=false;
    $result=$mode==='preview'?email_action('preview',['sample_mode'=>'slots','subject'=>'Aperçu {{first_name}}','body'=>"{{participant_name}}\n{{slot_details}}\n{{cancel_url}}\nTexte <script>sans exécution</script> {{signature}}"]):null;
    OpenFabLab_Emails::render($result);exit;
}

check(count(OpenFabLab_Emails::defaults())===6,'six defaults');
[$row,$animation,$extra]=OpenFabLab_Emails::sample();
foreach(array_keys(OpenFabLab_Emails::defaults())as$kind){
    $mail=OpenFabLab_Emails::compose($kind,$row,$animation,$extra);
    check(trim($mail['subject'])!==''&&trim($mail['body'])!==''&&!str_contains($mail['body'],'{{'),'default rendered '.$kind);
}
$mail=OpenFabLab_Emails::compose('confirmation',$row,$animation,$extra);
check(str_contains($mail['body'],'Camille EXEMPLE')&&str_contains($mail['body'],'OFL-EXEMPLE'),'name and existing identifier');
check(str_contains($mail['body'],'Durée : 120 minutes'),'whole duration');
check(!str_contains($mail['body'],'Créneau')&&!str_contains($mail['body'],'2099 à 10:00\n\nDurée'),'no useless whole slot line');
$row['public_id']=null;
check(str_contains(OpenFabLab_Emails::compose('confirmation',$row,$animation,$extra)['body'],'Identifiant : non renseigné'),'absent ID');
$row['public_id']='';
check(OpenFabLab_Emails::context($row,$animation)['public_id']==='non renseigné','public_id alias also has fallback');
check(OpenFabLab_Emails::context($row,$animation)['age_rule']==='10 ans (et accompagnement requis avant 15 ans)','age and accompaniment');
$animation['accompaniment_under_age']=0;
check(OpenFabLab_Emails::context($row,$animation)['age_rule']==='10 ans','age without accompaniment');
[$row,$animation,$extra]=OpenFabLab_Emails::sample(true);
$mail=OpenFabLab_Emails::compose('confirmation',$row,$animation,$extra);
check(str_contains($mail['body'],'Créneau : 10:30–10:50')&&str_contains($mail['body'],'Durée : 20 minutes'),'chosen slot, not gap/global duration');
check(OpenFabLab_Emails::context($row,$animation)['time']==='10:30','slot local timezone');
$bad=['subject'=>'{{unknown}}','body'=>'{{cancel_url}}'];
check(email_error('save',$bad),'unknown variable rejected');
check(email_error('save',['body'=>'{{first-name}} {{cancel_url}}']),'misspelled variable rejected');
check(email_error('save',['body'=>'{{ first_name }} {{cancel_url}}']),'spaced variable rejected clearly');
check(email_error('save',['body'=>'{{first_name {{cancel_url}}']),'malformed variable rejected');
check(email_error('save',['body'=>'{{offer_url}} {{cancel_url}}']),'wrong-model variable refused');
check(email_error('save',['body'=>'No link']),'cancellation link cannot be removed');
check(email_error('save',['email_model'=>'offer','body'=>'No offer link']),'offer link cannot be removed');
check(email_error('save',['subject'=>'']),'empty subject rejected');
check(email_error('save',['body'=>'']),'empty body rejected');
check(email_error('save',['subject'=>"X\r\nBcc: injected@example.invalid"]),'subject header injection refused');
check(email_error('save',['subject'=>['bad']]),'non-text template rejected');
check(email_error('save',['subject'=>chr(255)]),'invalid UTF8 refused');
check(empty($email_test_options),'invalid saves never write');
check(isset(email_action('signature',['signature'=>"Atelier EXEMPLE\ncontact@example.invalid"])['success']),'common signature saved');
check(isset(email_action('save')['success']),'custom model saved');
$stored=$email_test_options;$mail=OpenFabLab_Emails::compose('confirmation',$row,$animation,$extra);
check($mail['subject']==='Bonjour Camille EXEMPLE'&&str_contains($mail['body'],'contact@example.invalid'),'custom substitution and common signature');
$preview=email_action('preview',['sample_mode'=>'slots']);
check(isset($preview['preview']),'fictitious preview');
check($preview['draft']['subject']==='Bonjour {{participant_name}}','preview retains editable draft');
check($email_test_options===$stored&&!$mails,'preview never saves or sends');
$render=OpenFabLab_Emails::compose('confirmation',['first_name'=>'{{signature}}','last_name'=>"A\r\nBcc: nobody@example.invalid",'public_id'=>null]+$row,$animation,$extra);
check(!str_contains($render['subject'],"\n")&&str_contains($render['subject'],'{{signature}}'),'no recursive evaluation or header injection from values');
$preview=email_action('preview',['subject'=>'<b>Bonjour</b> {{first_name}}','body'=>"<script>alert('fixture')</script> {{cancel_url}}"]);
ob_start();OpenFabLab_Emails::render($preview);$html=ob_get_clean();
check(!str_contains($html,'<script>')&&!str_contains($html,'participant@example.invalid'),'safe preview, no real reservation fetch');
check(substr_count($html,'name="email_model"')===6,'six private forms');
check(str_contains($html,'Signature / coordonnées communes')&&str_contains($html,'{{public_id_or_not_provided}}'),'admin explanations');
check(email_error('reset'),'reset needs explicit confirmation');
check($email_test_options===$stored,'unconfirmed reset leaves data unchanged');
check(isset(email_action('reset',['reset_confirm'=>'yes'])['success']),'confirmed reset');
check(OpenFabLab_Emails::template('confirmation')===array_intersect_key(OpenFabLab_Emails::defaults()['confirmation'],['subject'=>1,'body'=>1]),'reset restores generic only');
check(OpenFabLab_Emails::signature()==="Atelier EXEMPLE\ncontact@example.invalid",'reset keeps common signature');
foreach(['save','signature','reset','preview','send_test']as$action){
    check(email_error($action,['_wpnonce'=>'bad']),'nonce '.$action);
}
check(email_error('save',['_wpnonce'=>[]]),'malformed nonce refused');
$email_admin=false;check(email_error('preview'),'non-admin cannot preview');
ob_start();OpenFabLab_Emails::render();check(ob_get_clean()==='','non-admin gets no template data');$email_admin=true;
$email_logged=false;check(email_error('signature'),'authentication required');$email_logged=true;
$_SERVER['REQUEST_METHOD']='GET';check(email_error('save'),'GET never changes settings');$_SERVER['REQUEST_METHOD']='POST';
check(email_error('send_test',['test_recipient'=>'invalid']),'test address validated');
check(isset(email_action('send_test',['test_recipient'=>'admin@example.invalid','sample_mode'=>'slots'])['success']),'fictitious test send');
check(count($mails)===1&&$mails[0][0]==='admin@example.invalid'&&str_starts_with($mails[0][1],'[TEST modèle OpenFabLab]'),'test labelled and correct recipient');
check(str_contains($mails[0][2],'Créneau : 10:30–10:50')&&!str_contains($mails[0][2],'token='),'test uses only fictional links');
check(email_error('send_test',['test_recipient'=>'admin@example.invalid']),'test rate limited');
check(count($mails)===1,'rate limit does not send');
$email_transients=[];$mail_fails=true;
check(email_error('send_test',['test_recipient'=>'admin@example.invalid']),'failed test reported');$mail_fails=false;
$email_transients=[];$mail_throws=true;
check(email_error('send_test',['test_recipient'=>'admin@example.invalid']),'mail-filter exception reported without private details');$mail_throws=false;
check(isset(email_action('save',['subject'=>'{{unknown}}'])['draft']),'validation error retains editable draft');
$email_test_options['openfablab_res_test_prefix']='[ESSAI]';
OpenFabLab_Emails::deliver('recipient@example.invalid','Sujet','Texte','test');
check(str_starts_with(end($mails)[1],'[ESSAI] '),'configured test prefix');
OpenFabLab_Emails::deliver('recipient@example.invalid','Sujet','Texte','production');
check(end($mails)[1]==='Sujet','Normal no test prefix');
check(in_array('Content-Type: text/plain; charset=UTF-8',end($mails)[3],true),'UTF8 plain text transport');
$email_test_options['openfablab_res_email_settings']['templates']['confirmation']=['subject'=>'','body'=>''];
check(OpenFabLab_Emails::compose('confirmation',$row,$animation,$extra)['subject']!=='','corrupt option falls back');

// Real booking/offer/reminder/cancellation dispatch uses each customised model.
foreach(array_keys(OpenFabLab_Emails::defaults())as$kind){
    $link=$kind==='offer'?'{{offer_url}} {{offer_deadline}}':(in_array($kind,['confirmation','waitlist','reminder_one','reminder_two'],true)?'{{cancel_url}}':'');
    check(isset(email_action('save',['email_model'=>$kind,'subject'=>'CUSTOM-'.$kind.' {{animation_title}}','body'=>"{{participant_name}}\n{{slot_details}}\n$link\n{{signature}}"])['success']),'customise '.$kind);
}
$mails=[];check(publish(payload(90,1))===['ok'=>true],'dispatch fixture');
$slot=OpenFabLab_Slots::catalogue(animation(90))[0]['slot_uuid'];
check(reserve($slot,100,['service_id'=>90])['status']==='confirmed','confirmation dispatch');
check(str_contains(end($mails)[1],'CUSTOM-confirmation'),'confirmation template used');
check(reserve($slot,101,['service_id'=>90])['status']==='waitlisted','waitlist dispatch');
check(str_contains(end($mails)[1],'CUSTOM-waitlist'),'waitlist template used');
$first=named(100);$first_token=token($first['id']);$before=count($mails);
check(OpenFabLab_Bookings::cancel($first['uuid'],$first_token)===true,'public cancellation succeeds');
$sent=array_slice($mails,$before);
check(count($sent)===2&&count(array_filter($sent,fn($m)=>str_contains($m[1],'CUSTOM-cancellation')))===1
    &&count(array_filter($sent,fn($m)=>str_contains($m[1],'CUSTOM-offer')))===1,'cancel and offer, one each');
check(!str_contains(end($mails)[2],'token='),'cancellation confirmation exposes no action token');
$before=count($mails);check(is_wp_error(OpenFabLab_Bookings::cancel($first['uuid'],$first_token))&&count($mails)===$before,'cancel retry no duplicate');
$waiter=named(101);$offer_token=token($waiter['id']);
check(OpenFabLab_Bookings::respond_offer($waiter['uuid'],$offer_token,true)===true,'offer accepted');
check(str_contains(end($mails)[1],'CUSTOM-confirmation'),'offer acceptance uses confirmation');
$before=count($mails);check(is_wp_error(OpenFabLab_Bookings::respond_offer($waiter['uuid'],$offer_token,true))&&count($mails)===$before,'acceptance retry no duplicate');
check(OpenFabLab_API::sync_commands(new WP_REST_Request(['environment'=>'test','uuid'=>$waiter['uuid'],'action'=>'cancel']))===['ok'=>true],'NAS cancellation succeeds');
check(count($mails)===$before,'NAS internal cancellation has no confirmation');

// Due reminders choose separate templates, use selected slot, honour zero/flags.
foreach([92=>1,93=>0]as$service=>$second){
    $p=payload($service,1);$p['animation']['minimum_age']=0;$p['animation']['accompaniment_under_age']=0;
    check(publish($p)===['ok'=>true],'reminder fixture');
    $a=animation($service);$catalog=OpenFabLab_Slots::catalogue($a);
    foreach($catalog as$i=>&$s){$s['starts_at']=gmdate('Y-m-d H:i:s',time()+1800+$i*1800);$s['ends_at']=gmdate('Y-m-d H:i:s',time()+3000+$i*1800);}unset($s);
    $wpdb->update('wp_openfablab_animations',['starts_at'=>gmdate('Y-m-d H:i:s',time()+1800),'ends_at'=>gmdate('Y-m-d H:i:s',time()+10000),
        'slots_json'=>json_encode($catalog),'reminder_one_hours'=>2,'reminder_two_hours'=>$second],['id'=>$a['id']]);
    check(reserve($catalog[0]['slot_uuid'],$service,['service_id'=>$service])['status']==='confirmed','reminder booked');
}
$before=count($mails);OpenFabLab_Bookings::run_due_tasks();$due=array_slice($mails,$before);
check(count($due)===3,'two reminders plus only first when second zero');
check(count(array_filter($due,fn($m)=>str_contains($m[1],'CUSTOM-reminder_one')))===2,'distinct first template');
check(count(array_filter($due,fn($m)=>str_contains($m[1],'CUSTOM-reminder_two')))===1,'distinct second template');
$chosen=OpenFabLab_Emails::context(named(92),animation(92));
check(str_contains($due[0][2],$chosen['slot_details']),'reminder chosen slot');
$before=count($mails);OpenFabLab_Bookings::run_due_tasks();check(count($mails)===$before,'sent reminders idempotent');

// A minor + companion sharing an address receives only one cancellation confirmation.
$p=payload(95,2);$year=(int)gmdate('Y')+1;$p['animation']['service_date']="$year-10-08";
foreach($p['animation']['slots']as&$s){$s['starts_at']=str_replace('2099-',"$year-",$s['starts_at']);$s['ends_at']=str_replace('2099-',"$year-",$s['ends_at']);}unset($s);
check(publish($p)===['ok'=>true],'companion fixture');$slot=OpenFabLab_Slots::catalogue(animation(95))[0]['slot_uuid'];
$result=reserve($slot,95,['service_id'=>95,'birth_year'=>$year-12,'email'=>'family@example.invalid',
    'companion'=>['first_name'=>'Adulte','last_name'=>'FICTIF','birth_year'=>1990,'email'=>'family@example.invalid','phone'=>'0600000000']]);
check($result['count']===2,'minor and adult two places');$family=named(95);$before=count($mails);
check(OpenFabLab_Bookings::cancel($family['uuid'],token($family['id']))===true,'family cancellation');
check(count($mails)===$before+1&&str_contains(end($mails)[1],'CUSTOM-cancellation'),'same group recipient not duplicated');
check(OpenFabLab_Slots::used(animation(95),$slot)===0,'both family seats freed');
// Failed cancellation writes cannot send a success message or commit partial state.
check(publish(payload(96,1))===['ok'=>true],'rollback fixture');
$slot=OpenFabLab_Slots::catalogue(animation(96))[0]['slot_uuid'];
check(reserve($slot,96,['service_id'=>96])['status']==='confirmed','rollback booking');
$b=named(96);$cancel_token=token($b['id']);$before=count($mails);
$wpdb->fail='UPDATE wp_openfablab_tokens SET used_at';
check(is_wp_error(OpenFabLab_Bookings::cancel($b['uuid'],$cancel_token)),'token invalidation failure refused');
$wpdb->fail='';
check(named(96)['status']==='confirmed'&&count($mails)===$before,'rollback and no false cancellation email');
check(is_wp_error(OpenFabLab_Bookings::cancel($b['uuid'],str_repeat('0',64)))&&count($mails)===$before,'invalid link never sends');
check(OpenFabLab_Bookings::cancel($b['uuid'],$cancel_token)===true,'retry after rollback works');
check(count($mails)===$before+1,'one real cancellation after recovered transaction');
check(publish(payload(97,2,10,'production','whole'))===['ok'=>true],'classic Normal fixture');
check(reserve(null,97,['service_id'=>97,'environment'=>'production'])['status']==='confirmed','classic Normal booking');
check(!str_contains(end($mails)[1],'[ESSAI]')&&!str_contains(end($mails)[2],'Créneau :'),'classic mail no test prefix or slot line');
$before=count($mails);$b=named(97);
check(OpenFabLab_Bookings::cancel($b['uuid'],token($b['id']))===true&&count($mails)===$before+1,'classic cancellation confirmation');
check(!str_contains(end($mails)[1],'[ESSAI]'),'Normal cancellation keeps Normal transport');
check($wpdb->pdo->query('PRAGMA integrity_check')->fetchColumn()==='ok','fixture integrity');
echo "$tests email PHP checks passed\n";
