<?php
// Actual plugin business logic + SQL transactions. Fictional SQLite fixtures only.
define('ABSPATH',__DIR__); define('ARRAY_A','ARRAY_A');
define('HOUR_IN_SECONDS',3600); define('DAY_IN_SECONDS',86400); define('YEAR_IN_SECONDS',365*86400);
class WP_Error {
    public function __construct(public $code,public $message,public $data=[]) {}
    public function get_error_message(){return $this->message;}
}
class WP_REST_Request {public function __construct(private $data){} public function get_body(){return json_encode($this->data);}}
class WP_REST_Response {public function __construct(public $data){} public function header(...$args){}}
function is_wp_error($v){return $v instanceof WP_Error;}
function get_option($n,$d=''){return $GLOBALS['email_test_options'][$n]??($n==='openfablab_res_sync_secret'?'fictional-only-slot-fixture':$d);}
function update_option($n,$v,...$args){$GLOBALS['email_test_options'][$n]=$v;return true;}
function sanitize_text_field($v){return trim(strip_tags((string)$v));}
function sanitize_email($v){return filter_var($v,FILTER_VALIDATE_EMAIL)?$v:'';}
function is_email($v){return filter_var($v,FILTER_VALIDATE_EMAIL);}
function wp_kses_post($v){return $v;}
function wp_json_encode($v){return json_encode($v);}
function wp_generate_uuid4(){return sprintf('10000000-0000-4000-8000-%012d',++$GLOBALS['uuid']);}
function current_time(...$args){return gmdate('Y-m-d H:i:s');}
function wp_date($f,$t=null,$z=null){return(new DateTimeImmutable('@'.($t??time())))->setTimezone($z??new DateTimeZone('Europe/Paris'))->format($f);}
function wp_mail(...$args){if($GLOBALS['mail_throws']??false)throw new RuntimeException('fixture mail failure');$GLOBALS['mails'][]=$args;return !($GLOBALS['mail_fails']??false);}
function get_bloginfo($v){return 'Atelier fictif';}
function admin_url($v){return 'https://example.invalid/'.$v;}
function home_url($v){return 'https://example.invalid'.$v;}
function add_query_arg($a,$b=null,$c=null){return is_array($a)?$b.'?'.http_build_query($a):$c.'?'.http_build_query([$a=>$b]);}
function esc_url_raw($v){return $v;}
class SlotDatabase {
    public $pdo,$prefix='wp_',$history=[],$fail='',$last_error='';
    public function __construct(){
        $this->pdo=new PDO('sqlite::memory:');$this->pdo->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
        $this->pdo->exec("CREATE TABLE wp_openfablab_animations(id INTEGER PRIMARY KEY, environment TEXT, service_id INTEGER, title TEXT, description TEXT, starts_at TEXT, ends_at TEXT, timezone TEXT, capacity INTEGER, minimum_age INTEGER, audience TEXT, accompaniment_under_age INTEGER, waitlist_enabled INTEGER, close_minutes INTEGER, signup_open_at TEXT, reminder_one_hours INTEGER, reminder_two_hours INTEGER, offer_hours INTEGER, last_offer_hours INTEGER, published INTEGER, updated_at TEXT, booking_mode TEXT DEFAULT 'whole', slot_duration_minutes INTEGER DEFAULT 20, slot_gap_minutes INTEGER DEFAULT 0, slot_capacity INTEGER DEFAULT 1, slots_json TEXT DEFAULT '[]', UNIQUE(environment,service_id));
        CREATE TABLE wp_openfablab_reservations(id INTEGER PRIMARY KEY, uuid TEXT UNIQUE, environment TEXT, animation_id INTEGER, first_name TEXT, last_name TEXT, birth_year INTEGER, email TEXT, phone TEXT, status TEXT, link_status TEXT, public_id TEXT, group_uuid TEXT, slot_uuid TEXT, identity_key TEXT, source TEXT, is_present INTEGER, created_at TEXT, updated_at TEXT, offer_expires_at TEXT, reminder_one_sent_at TEXT, reminder_two_sent_at TEXT);
        CREATE TABLE wp_openfablab_directory(id INTEGER PRIMARY KEY, environment TEXT, active INTEGER, public_id TEXT, email_hmac TEXT, phone_hmac TEXT, updated_at TEXT);
        CREATE TABLE wp_openfablab_events(id INTEGER PRIMARY KEY, environment TEXT, event_type TEXT, reservation_uuid TEXT, created_at TEXT);
        CREATE TABLE wp_openfablab_tokens(id INTEGER PRIMARY KEY, reservation_uuid TEXT, token_type TEXT, token_hash TEXT, expires_at TEXT, created_at TEXT, used_at TEXT);
        CREATE TABLE wp_openfablab_nonces(nonce_hash TEXT, expires_at TEXT);");
    }
    public function prepare($sql,...$args){$i=0;return preg_replace_callback('/%[sd]/',function($m)use($args,&$i){$v=$args[$i++];return $m[0]==='%d'?(string)(int)$v:$this->pdo->quote((string)$v);},$sql);}
    private function execute($sql){
        $this->history[]=$sql;$this->last_error='';
        if($this->fail&&str_contains($sql,$this->fail)){$this->last_error='fixture failure';return false;}
        $sql=preg_replace('/ FOR UPDATE$/','',$sql);if($sql==='START TRANSACTION')$sql='BEGIN TRANSACTION';
        return $this->pdo->query($sql);
    }
    public function get_row($sql,$mode=null){if(str_contains($sql,'SHOW TABLE STATUS'))return(object)['Engine'=>'InnoDB'];$q=$this->execute($sql);return$q?$q->fetch(PDO::FETCH_ASSOC):null;}
    public function get_results($sql,$mode=null){$q=$this->execute($sql);return$q?$q->fetchAll(PDO::FETCH_ASSOC):[];}
    public function get_var($sql){$q=$this->execute($sql);return$q?$q->fetchColumn():null;}
    public function query($sql){$q=$this->execute($sql);return$q===false?false:$q->rowCount();}
    public function insert($table,$row,$format=[]){$q=$this->execute('INSERT INTO '.$table.' ('.implode(',',array_keys($row)).') VALUES ('.implode(',',array_map(fn($v)=>$v===null?'NULL':$this->pdo->quote((string)$v),array_values($row))).')');return$q===false?false:$q->rowCount();}
    public function update($table,$row,$where){$set=[];$filters=[];foreach($row as$key=>$v)$set[]=$key.'='.($v===null?'NULL':$this->pdo->quote((string)$v));foreach($where as$key=>$v)$filters[]=$key.($v===null?' IS NULL':'='.$this->pdo->quote((string)$v));$q=$this->execute('UPDATE '.$table.' SET '.implode(',',$set).' WHERE '.implode(' AND ',$filters));return$q===false?false:$q->rowCount();}
}
$plugin=dirname(__DIR__).'/wordpress/openfablab-reservations/includes/';
foreach(['database','slots','emails','bookings','api']as$name)require$plugin.'class-openfablab-'.$name.'.php';
$tests=0;$uuid=0;$mails=[];$wpdb=new SlotDatabase();
function check($ok,$label){if(!$ok)throw new RuntimeException($label);$GLOBALS['tests']++;}
function payload($service=1,$capacity=2,$gap=10,$env='test',$mode='slots'){
    $slots=[];for($m=0;$m+20<=120;$m+=20+$gap){$a=(new DateTimeImmutable('2099-10-08T08:00:00Z'))->modify("+$m minutes");$slots[]=['slot_uuid'=>sprintf('20000000-0000-4000-8000-%012d',$service*100+$m),'starts_at'=>$a->format('c'),'ends_at'=>$a->modify('+20 minutes')->format('c'),'capacity'=>$capacity];}
    $a=['environment'=>$env,'service_id'=>$service,'title'=>'Découverte casque VR','description'=>'Fixture','service_date'=>'2099-10-08','start_time'=>'10:00','end_time'=>'12:00','timezone'=>'Europe/Paris','capacity'=>$mode==='slots'?count($slots)*$capacity:$capacity,'minimum_age'=>6,'audience'=>'all','accompaniment_under_age'=>15,'waitlist_enabled'=>true,'close_minutes'=>0,'signup_open_at'=>null,'reminder_one_hours'=>24,'reminder_two_hours'=>0,'published'=>true,'booking_mode'=>$mode,'slot_duration_minutes'=>20,'slot_gap_minutes'=>$gap,'slot_capacity'=>$capacity,'slots'=>$slots];
    return['environment'=>$env,'service_id'=>$service,'animation'=>$a];
}
function publish($p){return OpenFabLab_API::sync_animations(new WP_REST_Request($p));}
function animation($id=1,$env='test'){global$wpdb;return$wpdb->get_row($wpdb->prepare('SELECT * FROM wp_openfablab_animations WHERE service_id=%d AND environment=%s',$id,$env),ARRAY_A);}
function reserve($slot,$n=1,$extra=[]){return OpenFabLab_Bookings::reserve($extra+['environment'=>'test','service_id'=>1,'slot_uuid'=>$slot,'first_name'=>'Personne'.$n,'last_name'=>'FICTIF','birth_year'=>1990,'email'=>"fixture$n@example.invalid",'phone'=>'0600000000']);}
function booking($id){global$wpdb;return$wpdb->get_row('SELECT * FROM wp_openfablab_reservations WHERE id='.(int)$id,ARRAY_A);}
function token($id){global$mails;foreach(array_reverse($mails)as$mail)if(preg_match('/booking='.preg_quote(booking($id)['uuid'],'/').'&token=([a-f0-9]{64})/',$mail[2],$m))return$m[1];throw new RuntimeException('fixture token missing');}
check(publish(payload())===['ok'=>true],'publish slot animation');
$a=animation();$slots=OpenFabLab_Slots::catalogue($a);$s0=$slots[0]['slot_uuid'];$s1=$slots[1]['slot_uuid'];
check(count($slots)===4,'four slots with gap');
check(publish(payload(2,1,0))===['ok'=>true]&&count(OpenFabLab_Slots::catalogue(animation(2)))===6,'six slots without gap');
check(is_wp_error(reserve(null)),'slot mandatory');check(is_wp_error(reserve('invalid')),'bad slot');
check(is_wp_error(reserve(OpenFabLab_Slots::catalogue(animation(2))[0]['slot_uuid'])),'foreign slot');
check(reserve($s0)['status']==='confirmed','first seat');check(reserve($s0,2)['status']==='confirmed','second seat');
check(reserve($s0,3)['status']==='waitlisted','third waits');check(OpenFabLab_Slots::used($a,$s0)===2,'capacity two');
check(OpenFabLab_Slots::used($a,$s1)===0,'other slot unchanged');check(reserve($s1,4)['status']==='confirmed','other slot available');
check(is_wp_error(reserve($s0,1)),'duplicate same slot rejected');check(reserve($s1,1)['status']==='confirmed','same person other slot allowed');
check(str_contains($mails[0][2],'Date et heure : 08/10/2099 à 10:00')&&str_contains($mails[0][2],'Créneau : 10:00–10:20'),'confirmation slot end excludes gap');
check(booking(1)['slot_uuid']===$s0&&booking(3)['slot_uuid']===$s0,'stable slot stored');
$before1=OpenFabLab_Slots::used($a,$s1);
check(OpenFabLab_Bookings::cancel(booking(1)['uuid'],token(1))===true,'cancel first slot');
check(booking(1)['status']==='cancelled'&&booking(3)['status']==='offer_pending','only same queue promoted');
check(OpenFabLab_Slots::used($a,$s1)===$before1,'other occupancy unchanged');
check(OpenFabLab_Bookings::respond_offer(booking(3)['uuid'],token(3),true)===true,'accept slot offer');
check(booking(3)['status']==='confirmed','offered seat confirmed');
$change=payload();$change['animation']['slot_gap_minutes']=0;
check(is_wp_error(publish($change)),'timing protected after booking');
check(is_wp_error(publish(payload(1,1))),'capacity reduction protected');
check(is_wp_error(publish(payload(1,8,10,'test','whole'))),'mode protected');
check(publish(payload(1,3))===['ok'=>true],'capacity increase allowed');
check(OpenFabLab_Slots::catalogue(animation())[0]['slot_uuid']===$s0,'ID unchanged on capacity increase');
check(publish(payload(3,1,10,'production'))===['ok'=>true],'Normal independent publication');
$test=OpenFabLab_Bookings::public_animations('test');$normal=OpenFabLab_Bookings::public_animations('production');
check(count($test)===2&&count($normal)===1,'Normal Test separated');
check($test[0]['slots'][0]['available']===1,'per-slot availability recalculated');
check(!str_contains(json_encode($test),'fixture1@example.invalid'),'public catalogue no identity');
$companion=['first_name'=>'Adulte','last_name'=>'FICTIF','birth_year'=>1990,'email'=>'adult@example.invalid','phone'=>'0600000000'];
// A real minor scenario on a future date, not a hypothetical birth in 2090.
$future=(int)gmdate('Y')+1;
foreach([20=>2,21=>1]as$service=>$capacity){
    $p=payload($service,$capacity);$p['animation']['service_date']="$future-10-08";
    foreach($p['animation']['slots']as&$slot){foreach(['starts_at','ends_at']as$key)$slot[$key]=str_replace('2099-',"$future-",$slot[$key]);}unset($slot);
    check(publish($p)===['ok'=>true],'minor fixture publication');
}
$minor_slot=OpenFabLab_Slots::catalogue(animation(20))[0]['slot_uuid'];
check(reserve($minor_slot,6,['service_id'=>20,'birth_year'=>$future-9,'companion'=>$companion])['count']===2,'minor and adult same slot');
$pair=$wpdb->get_results("SELECT * FROM wp_openfablab_reservations WHERE group_uuid IS NOT NULL",ARRAY_A);
check(count($pair)===2&&$pair[0]['slot_uuid']===$pair[1]['slot_uuid'],'pair stable same slot');
check(OpenFabLab_Slots::used(animation(20),$minor_slot)===2,'two companion seats');
check(is_wp_error(reserve(OpenFabLab_Slots::catalogue(animation(21))[0]['slot_uuid'],7,['service_id'=>21,'birth_year'=>$future-9,'companion'=>$companion])),'pair cannot fit capacity one');
foreach(['slot_duration_minutes'=>0,'slot_gap_minutes'=>-1,'slot_capacity'=>0]as$key=>$v){$p=payload(4);$p['animation'][$key]=$v;check(is_wp_error(publish($p)),'invalid '.$key);}
$p=payload(4);array_pop($p['animation']['slots']);check(is_wp_error(publish($p)),'incomplete catalogue refused');
$p=payload(4);$p['animation']['slots'][0]['ends_at']='2099-10-08T08:30Z';check(is_wp_error(publish($p)),'duration mismatch refused');
$p=payload(4);$p['animation']['end_time']='10:10';check(is_wp_error(publish($p)),'too short');
$events=OpenFabLab_API::sync_events(new WP_REST_Request(['environment'=>'test','cursor'=>0]));
check($events->data['events'][0]['booking']['slot_uuid']===$s0,'signed events carry slot');
check(OpenFabLab_API::capabilities(new WP_REST_Request([]))['animation_slots_v1']===true,'capability handshake');
$wpdb->fail='INSERT INTO wp_openfablab_reservations';$n=(int)$wpdb->get_var('SELECT COUNT(*) FROM wp_openfablab_reservations');
check(is_wp_error(reserve($slots[3]['slot_uuid'],8)),'failed insert refused');$wpdb->fail='';
check((int)$wpdb->get_var('SELECT COUNT(*) FROM wp_openfablab_reservations')===$n,'failed transaction rollback');
check(count(array_filter($wpdb->history,fn($sql)=>str_contains($sql,'FOR UPDATE')))>10,'all capacity mutations use shared animation lock');
check(publish(payload(10,2,10,'test','whole'))===['ok'=>true],'classic publication');
check(reserve(null,10,['service_id'=>10])['status']==='confirmed','classic no slot needed');
check(is_wp_error(reserve($s0,11,['service_id'=>10])),'classic rejects slot');
check($wpdb->get_var('PRAGMA integrity_check')==='ok','fixture integrity');
check($wpdb->get_results('PRAGMA foreign_key_check')===[],'fixture FK');

// Signed manual confirmation must not borrow free seats from another slot.
check(reserve($s1,50)['status']==='confirmed','fill target slot');
check(reserve($s1,51)['status']==='waitlisted','target overflow waits');
$waiting=$wpdb->get_row("SELECT * FROM wp_openfablab_reservations WHERE first_name='Personne51'",ARRAY_A);
$command=['environment'=>'test','uuid'=>$waiting['uuid'],'action'=>'confirm'];
$result=OpenFabLab_API::sync_commands(new WP_REST_Request($command));
check(($result['confirmation']??'')==='refused'&&$result['reason']==='capacity','manual confirm per-slot refusal');
check(OpenFabLab_Slots::used(animation(),$s1)===3,'refusal leaves occupancy unchanged');
check(OpenFabLab_API::sync_commands(new WP_REST_Request($command+['capacity_override'=>true]))===['ok'=>true],'explicit signed administrator override');
check(OpenFabLab_Slots::used(animation(),$s1)===4,'override confined to target');

// An expired offer processes only that slot, not a newly free other queue.
check(publish(payload(40,1))===['ok'=>true],'expiry fixture');
$q=OpenFabLab_Slots::catalogue(animation(40));$q0=$q[0]['slot_uuid'];$q1=$q[1]['slot_uuid'];
foreach([[$q0,60],[$q0,61],[$q0,62],[$q1,63],[$q1,64]]as[$slot,$n]){check(!is_wp_error(reserve($slot,$n,['service_id'=>40])),'expiry reservation');}
function named($n){global$wpdb;return$wpdb->get_row("SELECT * FROM wp_openfablab_reservations WHERE first_name='Personne".(int)$n."'",ARRAY_A);}
check(OpenFabLab_Bookings::cancel(named(60)['uuid'],token(named(60)['id']))===true,'first queue offer');
check(named(61)['status']==='offer_pending','FIFO offer created');
$wpdb->update('wp_openfablab_reservations',['offer_expires_at'=>'2000-01-01 00:00:00'],['uuid'=>named(61)['uuid']]);
$wpdb->update('wp_openfablab_reservations',['status'=>'cancelled'],['uuid'=>named(63)['uuid']]);
OpenFabLab_Bookings::run_due_tasks();
check(named(61)['status']==='expired','offer expired');check(named(62)['status']==='offer_pending','same queue next offer');
check(named(64)['status']==='waitlisted','other free queue not promoted by this expiry');
check(OpenFabLab_Slots::used(animation(40),$q1)===0,'other queue no occupied seat');

// Reminder timing and cancellation cutoff use the slot, not the global start.
$p=payload(41,1);check(publish($p)===['ok'=>true],'reminder fixture');$r=animation(41);
$catalog=OpenFabLab_Slots::catalogue($r);
foreach($catalog as$i=>&$slot){$slot['starts_at']=gmdate('Y-m-d H:i:s',time()+3600+$i*1800);$slot['ends_at']=gmdate('Y-m-d H:i:s',time()+4800+$i*1800);}unset($slot);
$wpdb->update('wp_openfablab_animations',['starts_at'=>gmdate('Y-m-d H:i:s',time()-600),'ends_at'=>gmdate('Y-m-d H:i:s',time()+12000),
    'slots_json'=>json_encode($catalog),'minimum_age'=>0,'accompaniment_under_age'=>0],['id'=>$r['id']]);
check(reserve($catalog[2]['slot_uuid'],70,['service_id'=>41])['status']==='confirmed','later slot bookable during global animation');
$before_mail=count($mails);OpenFabLab_Bookings::run_due_tasks();
check(count($mails)===$before_mail+1,'one due reminder');
$chosen=OpenFabLab_Emails::context(named(70),animation(41));
check(str_contains(end($mails)[2],$chosen['slot_details'])&&str_contains(end($mails)[2],$chosen['date'].' à '.$chosen['time']),'reminder exact chosen slot');
check(OpenFabLab_Bookings::cancel(named(70)['uuid'],token(named(70)['id']))===true,'later slot cancellation despite past global start');
check(named(70)['status']==='cancelled','slot cancelled');
// A one-minute rotation over twelve hours is valid in both applications.
$p=payload(42,1,0);$p['animation']['start_time']='00:00';$p['animation']['end_time']='12:00';
$p['animation']['slot_duration_minutes']=1;$p['animation']['capacity']=720;$p['animation']['slots']=[];
$begin=new DateTimeImmutable('2099-10-07T22:00:00Z');
for($i=0;$i<720;$i++){
    $start=$begin->modify("+$i minutes");
    $p['animation']['slots'][]=['slot_uuid'=>sprintf('30000000-0000-4000-8000-%012d',$i+1),
        'starts_at'=>$start->format('c'),'ends_at'=>$start->modify('+1 minute')->format('c'),'capacity'=>1];
}
check(publish($p)===['ok'=>true]&&count(OpenFabLab_Slots::catalogue(animation(42)))===720,'valid long slot catalogue');
$wpdb->fail='SELECT COUNT(*) FROM wp_openfablab_reservations WHERE animation_id';
$thrown=false;try{OpenFabLab_Slots::used(animation(),$s0);}catch(RuntimeException $e){$thrown=true;}
check($thrown,'failed capacity count never becomes zero');
$thrown=false;try{OpenFabLab_Slots::protect_update(animation(),animation());}catch(RuntimeException $e){$thrown=true;}
check($thrown,'failed booking history check never allows editing');
$wpdb->fail='';$wpdb->last_error='';
echo "$tests slot PHP checks passed\n";
