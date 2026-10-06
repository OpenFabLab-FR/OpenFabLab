<?php
if (!defined('ABSPATH')) { exit; }

/** Temporary transport only: NO capacity, identity or family business rules. */
final class OpenFabLab_Relay {
    private const TYPES = ['identify','contact','reserve','view','cancel','accept','decline'];
    private static $signed = [];
    private static function secret() { return (string) get_option('openfablab_res_sync_secret', ''); }
    private static function env($data) {
        $value = $data['environment'] ?? '';
        if (!in_array($value, ['production','test'], true)) { throw new InvalidArgumentException('Environnement invalide.'); }
        return $value;
    }
    private static function body($request, $maximum=32768) {
        if (strlen($request->get_body()) > $maximum) { throw new InvalidArgumentException('Demande trop volumineuse.'); }
        $value = json_decode($request->get_body(), true);
        if (!is_array($value)) { throw new InvalidArgumentException('Demande invalide.'); }
        return $value;
    }
    private static function error($message = 'La demande n’a pas pu être enregistrée.', $status = 503) {
        return new WP_Error('openfablab_relay', $message, ['status'=>$status]);
    }
    private static function reply($value) {
        $response = new WP_REST_Response($value);
        $response->header('Cache-Control','private, no-store, max-age=0');
        $response->header('Referrer-Policy','no-referrer');
        $response->header('X-Robots-Tag','noindex, nofollow');
        return $response;
    }
    public static function authenticated($request, $nonce) { self::$signed[spl_object_id($request)] = $nonce; }
    public static function serve($served, $result, $request, $server) {
        if (strpos($request->get_route(),'/openfablab/v1/')===0) {
            // The public browser uses same-origin WordPress only. Core uses
            // signed server-to-server HTTPS and does not need browser CORS.
            foreach (['Access-Control-Allow-Origin','Access-Control-Allow-Credentials','Access-Control-Allow-Methods','Access-Control-Allow-Headers'] as $header) { header_remove($header); }
        }
        $id=spl_object_id($request);
        if ($served || !isset(self::$signed[$id])) { return $served; }
        $raw=wp_json_encode($result->get_data(), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        $stamp=(string)time(); $nonce=self::$signed[$id]; unset(self::$signed[$id]);
        $canonical="response/v1\n$stamp\n$nonce\n".$request->get_route()."\n".$result->get_status()."\n".hash('sha256',$raw);
        $server->send_header('X-OpenFabLab-Response-Timestamp',$stamp);
        $server->send_header('X-OpenFabLab-Response-Nonce',$nonce);
        $server->send_header('X-OpenFabLab-Response-Signature',hash_hmac('sha256',$canonical,self::secret()));
        $server->send_header('Cache-Control','private, no-store');
        echo $raw; return true;
    }
    private static function key() {
        if (!self::secret()) { throw new RuntimeException('Connexion non configurée.'); }
        return hash_hmac('sha256','relay-storage/v1|'.wp_salt('auth'),self::secret(),true);
    }
    private static function encrypt($value) {
        $iv=random_bytes(12); $tag='';
        $data=openssl_encrypt($value,'aes-256-gcm',self::key(),OPENSSL_RAW_DATA,$iv,$tag,'openfablab-relay/v1');
        if ($data===false) { throw new RuntimeException('Stockage indisponible.'); }
        return base64_encode($iv.$tag.$data);
    }
    private static function decrypt($value) {
        $bytes=base64_decode($value,true);
        if ($bytes===false || strlen($bytes)<28) { throw new RuntimeException('Stockage indisponible.'); }
        $raw=openssl_decrypt(substr($bytes,28),'aes-256-gcm',self::key(),OPENSSL_RAW_DATA,substr($bytes,0,12),substr($bytes,12,16),'openfablab-relay/v1');
        if ($raw===false) { throw new RuntimeException('Stockage indisponible.'); }
        return $raw;
    }
    public static function install($collation) {
        $catalogues=OpenFabLab_Database::table('relay_catalogues');
        $actions=OpenFabLab_Database::table('relay_actions');
        dbDelta("CREATE TABLE $catalogues (
            environment varchar(12) NOT NULL,
            catalogue_json longtext NOT NULL,
            received_at bigint(20) NOT NULL,
            PRIMARY KEY  (environment)
        ) ENGINE=InnoDB $collation;");
        dbDelta("CREATE TABLE $actions (
            seq bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            action_id char(48) NOT NULL,
            environment varchar(12) NOT NULL,
            action_type varchar(12) NOT NULL,
            session_hash char(64) NOT NULL,
            request_key char(48) NOT NULL,
            payload_hash char(64) NOT NULL,
            payload_cipher longtext DEFAULT NULL,
            state varchar(12) NOT NULL DEFAULT 'pending',
            attempts int(11) NOT NULL DEFAULT 0,
            lease_id char(48) DEFAULT NULL,
            lease_until bigint(20) DEFAULT NULL,
            result_cipher longtext DEFAULT NULL,
            result_hash char(64) DEFAULT NULL,
            result_ok tinyint(1) DEFAULT NULL,
            created_at bigint(20) NOT NULL,
            acknowledged_at bigint(20) DEFAULT NULL,
            expires_at bigint(20) NOT NULL,
            PRIMARY KEY  (seq),
            UNIQUE KEY action_id (action_id),
            UNIQUE KEY session_request (environment,session_hash,request_key),
            KEY queue_order (environment,state,seq),
            KEY expires_at (expires_at)
        ) ENGINE=InnoDB $collation;");
    }
    public static function register() {
        foreach (['catalogue','poll','results'] as $method) {
            register_rest_route('openfablab/v1','/outbound/'.$method,[
                'methods'=>'POST','callback'=>[__CLASS__,$method],
                'permission_callback'=>['OpenFabLab_API','private_permission']]);
        }
        register_rest_route('openfablab/v1','/public/session',[
            'methods'=>'GET','callback'=>[__CLASS__,'session'], 'permission_callback'=>'__return_true']);
        foreach (['status','link'] as $method) {
            register_rest_route('openfablab/v1','/public/'.$method,[
                'methods'=>'POST','callback'=>[__CLASS__,$method], 'permission_callback'=>[__CLASS__,'permission']]);
        }
    }
    private static function cookie() {
        $value=(string)($_COOKIE['ofl_relay_session'] ?? '');
        return preg_match('/^[a-f0-9]{64}$/D',$value) ? $value : '';
    }
    private static function session_hash() { return hash_hmac('sha256',self::cookie(),wp_salt('auth')); }
    public static function session($request) {
        try {
            if (!is_ssl() || !self::secret()) { return self::error('La connexion doit être configurée par l’équipe.'); }
            $env=self::env(['environment'=>$request->get_param('environment')]);
            $cookie=self::cookie();
            if (!$cookie) {
                $cookie=bin2hex(random_bytes(32));
                setcookie('ofl_relay_session',$cookie,['expires'=>time()+1200,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']);
            }
            $until=time()+1200;
            return self::reply(['csrf'=>$until.'.'.hash_hmac('sha256',"csrf/v1|$cookie|$env|$until",wp_salt('auth'))]);
        } catch (Throwable $error) { return self::error('Session indisponible.'); }
    }
    public static function permission($request) {
        try {
            if (!is_ssl()) { return self::error('Une connexion HTTPS est nécessaire.',403); }
            $body=self::body($request); $env=self::env($body);
            $origin=$request->get_header('origin');
            $site=wp_parse_url(home_url('/'));
            $expected=$site['scheme'].'://'.$site['host'].(isset($site['port'])?':'.$site['port']:'');
            $parts=explode('.',(string)$request->get_header('x-openfablab-csrf'));
            if (!is_ssl() || !self::cookie() || $origin!==$expected || count($parts)!==2
                || !ctype_digit($parts[0]) || (int)$parts[0]<time() || (int)$parts[0]>time()+1200
                || !hash_equals(hash_hmac('sha256','csrf/v1|'.self::cookie()."|$env|".$parts[0],wp_salt('auth')),$parts[1])) {
                return self::error('Cette session a expiré. Actualisez la page.',403);
            }
            // Session/IP rate limits: never store an IP or a contact in logs.
            $rate='ofl_relay_rate_'.hash_hmac('sha256',(string)($_SERVER['REMOTE_ADDR'] ?? ''),wp_salt('auth')).'_'.(string)intdiv(time(),60);
            $count=(int)get_transient($rate);
            if ($count>=120) { return self::error('Patientez avant de réessayer.',429); }
            set_transient($rate,$count+1,90);
            return true;
        } catch (Throwable $error) { return self::error('Demande invalide.',400); }
    }
    public static function public_catalogue($env) {
        global $wpdb;
        try {
            self::env(['environment'=>$env]);
            $row=$wpdb->get_row($wpdb->prepare('SELECT * FROM '.OpenFabLab_Database::table('relay_catalogues').' WHERE environment=%s',$env));
            if (!$row || $row->received_at<time()-900) { return self::error('Les inscriptions sont momentanément indisponibles. Réessayez plus tard.'); }
            return self::reply(['environment'=>$env,'updated_at'=>(int)$row->received_at,'animations'=>json_decode($row->catalogue_json,true),
                'notice'=>'Les disponibilités sont indicatives. Votre groupe est confirmé après vérification.']);
        } catch (Throwable $error) { return self::error('Catalogue indisponible.'); }
    }
    public static function enqueue($type, array $data) {
        global $wpdb;
        try {
            $env=self::env($data);
            if (!in_array($type,self::TYPES,true) || !self::cookie() || !self::secret()
                || !preg_match('/^[a-f0-9]{48}$/D',(string)($data['request_key'] ?? ''))) {
                return self::error('Demande invalide.',400);
            }
            if (in_array($type,['identify','contact','reserve'],true) && is_wp_error(self::public_catalogue($env))) {
                return self::error('Les inscriptions sont momentanément indisponibles. Réessayez plus tard.');
            }
            $client_key=$data['request_key']; unset($data['request_key']);
            if ($type==='identify') {
                $data['client_bucket']=hash_hmac('sha256',(string)($_SERVER['REMOTE_ADDR'] ?? ''),wp_salt('auth'));
            }
            $raw=wp_json_encode($data,JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
            if (strlen($raw)>16384) { return self::error('Demande trop volumineuse.',400); }
            $hash=hash('sha256',$raw); $session=self::session_hash();
            $id=substr(hash_hmac('sha256',"action/v1|$env|$session|$client_key",self::secret()),0,48);
            $table=OpenFabLab_Database::table('relay_actions');
            OpenFabLab_Database::assert_transactional();
            if ((int)$wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE environment=%s AND state IN ('pending','processing') AND expires_at>%d",$env,time()))>=5000) {
                return self::error('Le service est momentanément occupé. Réessayez plus tard.',429);
            }
            $ok=$wpdb->query($wpdb->prepare("INSERT IGNORE INTO $table (action_id,environment,action_type,session_hash,request_key,payload_hash,payload_cipher,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%d,%d)",$id,$env,$type,$session,$client_key,$hash,self::encrypt($raw),time(),time()+86400));
            if ($ok===false) { throw new RuntimeException(); }
            $prior=$wpdb->get_row($wpdb->prepare("SELECT action_type,payload_hash FROM $table WHERE action_id=%s AND environment=%s AND session_hash=%s",$id,$env,$session));
            if (!$prior || $prior->action_type!==$type || !hash_equals($prior->payload_hash,$hash)) { return self::error('Cette demande a déjà été utilisée pour un autre choix.',409); }
            return self::reply(['state'=>'pending','request_key'=>$client_key,'message'=>'Votre demande a bien été reçue. Vérification en cours…']);
        } catch (Throwable $error) { return self::error(); }
    }
    public static function status($request) {
        global $wpdb;
        try {
            $data=self::body($request); $env=self::env($data); $key=$data['request_key'] ?? '';
            if (!preg_match('/^[a-f0-9]{48}$/D',(string)$key)) { return self::error('Demande inconnue.',404); }
            $row=$wpdb->get_row($wpdb->prepare('SELECT * FROM '.OpenFabLab_Database::table('relay_actions').' WHERE environment=%s AND session_hash=%s AND request_key=%s',$env,self::session_hash(),$key));
            if (!$row) { return self::error('Demande inconnue.',404); }
            if ($row->expires_at<=time()) { return self::reply(['state'=>'expired','message'=>'Cette demande a expiré. Identifiez-vous à nouveau.']); }
            if ($row->state==='done' && $row->result_cipher) { return self::reply(['state'=>'done','result'=>json_decode(self::decrypt($row->result_cipher),true)]); }
            return self::reply(['state'=>'pending','message'=>'Vérification en cours…']);
        } catch (Throwable $error) { return self::error(); }
    }
    public static function catalogue($request) {
        global $wpdb;
        try {
            $data=self::body($request,1000000);$env=self::env($data);$items=$data['animations'] ?? null;
            if (($data['protocol_version'] ?? 0)!==4 || !is_array($items) || count($items)>100) { return self::error('Catalogue invalide.',400); }
            $allowed=['service_id','title','description','date','hours','minimum_age','booking_mode','slots','available','waitlist_enabled'];
            foreach ($items as $item) {
                if (!is_array($item) || array_diff(array_keys($item),$allowed) || array_diff($allowed,array_keys($item))) { return self::error('Catalogue invalide.',400); }
                if (!is_int($item['service_id']) || $item['service_id']<=0 || !is_array($item['slots']) || count($item['slots'])>100
                    || !is_int($item['available']) || $item['available']<0 || !is_bool($item['waitlist_enabled'])) { return self::error('Catalogue invalide.',400); }
                foreach (['title','description','date','hours','booking_mode'] as $field) {
                    if (!is_string($item[$field]) || strlen($item[$field])>12000) { return self::error('Catalogue invalide.',400); }
                }
                foreach ($item['slots'] as $slot) {
                    if (!is_array($slot) || array_diff(array_keys($slot),['slot_uuid','label','available'])) { return self::error('Catalogue invalide.',400); }
                }
            }
            $table=OpenFabLab_Database::table('relay_catalogues');
            $ok=$wpdb->query($wpdb->prepare("INSERT INTO $table VALUES(%s,%s,%d) ON DUPLICATE KEY UPDATE catalogue_json=VALUES(catalogue_json),received_at=VALUES(received_at)",$env,wp_json_encode($items),time()));
            if ($ok===false) { throw new RuntimeException(); }
            update_option('openfablab_relay_catalogue_'.$env,time(),false);
            return ['ok'=>true,'plugin_version'=>OPENFABLAB_RES_VERSION];
        } catch (Throwable $error) { return self::error('Catalogue non enregistré.'); }
    }
    private static function prune() {
        global $wpdb; $table=OpenFabLab_Database::table('relay_actions');
        $wpdb->query($wpdb->prepare("UPDATE $table SET payload_cipher=NULL,result_cipher=NULL,state='expired' WHERE expires_at<=%d AND state!='expired'",time()));
        $wpdb->query($wpdb->prepare("DELETE FROM $table WHERE expires_at<%d",time()-7*86400));
        $wpdb->query($wpdb->prepare('DELETE FROM '.OpenFabLab_Database::table('nonces').' WHERE expires_at<%s',gmdate('Y-m-d H:i:s')));
    }
    public static function maintenance() {
        // Expunge expired transport data even when the core is offline.
        // No historical booking, promotion, email or capacity operation.
        try { OpenFabLab_Database::assert_transactional();self::prune(); }
        catch (Throwable $error) { return; }
    }
    public static function poll($request) {
        global $wpdb;
        try {
            $data=self::body($request);$env=self::env($data);
            if (($data['protocol_version'] ?? 0)!==4) { return self::error('Versions incompatibles.',409); }
            OpenFabLab_Database::assert_transactional();
            self::prune(); $table=OpenFabLab_Database::table('relay_actions');
            if ($wpdb->query('START TRANSACTION')===false) { throw new RuntimeException(); }
            $rows=$wpdb->get_results($wpdb->prepare("SELECT * FROM $table WHERE environment=%s AND expires_at>%d AND (state='pending' OR (state='processing' AND lease_until<%d)) ORDER BY seq LIMIT 20 FOR UPDATE",$env,time(),time()));
            if ($wpdb->last_error) { throw new RuntimeException(); }
            $result=[];
            foreach ($rows as $row) {
                $lease=bin2hex(random_bytes(24));
                if ($wpdb->query($wpdb->prepare("UPDATE $table SET state='processing',attempts=attempts+1,lease_id=%s,lease_until=%d WHERE seq=%d",$lease,time()+60,$row->seq))!==1) { throw new RuntimeException(); }
                $result[]=['id'=>$row->action_id,'type'=>$row->action_type,'hash'=>$row->payload_hash,'payload_json'=>self::decrypt($row->payload_cipher),'lease'=>$lease];
            }
            if ($wpdb->query('COMMIT')===false) { throw new RuntimeException(); }
            update_option('openfablab_relay_poll_'.$env,time(),false);
            return ['protocol_version'=>4,'outbound_actions_v1'=>true,'actions'=>$result,'queue'=>self::queue_state($env)];
        } catch (Throwable $error) { $wpdb->query('ROLLBACK'); return self::error('Demandes indisponibles.'); }
    }
    public static function results($request) {
        global $wpdb;
        try {
            // Batch results contain only short, session-limited choices/receipts.
            $raw=$request->get_body();
            if (strlen($raw)>524288) { return self::error('Résultats invalides.',400); }
            $data=json_decode($raw,true);$env=self::env($data);
            $results=$data['results'] ?? null;
            if (($data['protocol_version'] ?? 0)!==4 || !is_array($results) || count($results)>20) { return self::error('Résultats invalides.',400); }
            $table=OpenFabLab_Database::table('relay_actions'); $ack=[];
            OpenFabLab_Database::assert_transactional();
            if ($wpdb->query('START TRANSACTION')===false) { throw new RuntimeException(); }
            foreach ($results as $item) {
                $row=$wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE environment=%s AND action_id=%s FOR UPDATE",$env,$item['id'] ?? ''));
                if (!$row || !hash_equals($row->payload_hash,(string)($item['hash'] ?? '')) || !is_array($item['result'] ?? null) || !is_bool($item['result']['ok'] ?? null)) { throw new RuntimeException(); }
                $json=wp_json_encode($item['result']);$digest=hash('sha256',$json);
                if ($row->state==='done') {
                    if (!hash_equals($row->result_hash,$digest)) { throw new RuntimeException(); }
                } else {
                    if ($row->state!=='processing' || !hash_equals($row->lease_id,(string)($item['lease'] ?? ''))) { throw new RuntimeException(); }
                    $ttl=in_array($row->action_type,['identify','contact','view'],true)?1200:86400;
                    if ($wpdb->query($wpdb->prepare("UPDATE $table SET state='done',result_cipher=%s,result_hash=%s,result_ok=%d,payload_cipher=NULL,acknowledged_at=%d,expires_at=%d WHERE seq=%d",self::encrypt($json),$digest,$item['result']['ok']?1:0,time(),time()+$ttl,$row->seq))!==1) { throw new RuntimeException(); }
                }
                $ack[]=$row->action_id;
            }
            if ($wpdb->query('COMMIT')===false) { throw new RuntimeException(); }
            update_option('openfablab_relay_results_'.$env,time(),false);
            return ['acknowledged'=>$ack];
        } catch (Throwable $error) { $wpdb->query('ROLLBACK');return self::error('Résultats non acquittés.'); }
    }
    private static function verify_link($link,$environment,$action) {
        if (!is_string($link) || strlen($link)>600 || !preg_match('/^([A-Za-z0-9_-]+)\.([a-f0-9]{64})$/D',$link,$match)
            || !hash_equals(hash_hmac('sha256',"link/v1\n".$match[1],self::secret()),$match[2])) { throw new InvalidArgumentException('Ce lien est invalide ou indisponible.'); }
        $data=json_decode(base64_decode(strtr($match[1],'-_','+/'),true),true);
        if (!is_array($data) || count($data)!==5 || ($data['v'] ?? 0)!==1 || ($data['e'] ?? '')!==$environment
            || !in_array($data['k'] ?? '',['manage','offer'],true) || !is_int($data['x'] ?? null)
            || !preg_match('/^[A-Za-z0-9_-]{40,80}$/D',(string)($data['t'] ?? ''))) { throw new InvalidArgumentException('Ce lien est invalide ou indisponible.'); }
        if ($data['x'] && $data['x']<=time()) { throw new InvalidArgumentException('Cette proposition a expiré. Aucune place n’a été confirmée.'); }
        if (in_array($action,['accept','decline'],true) && $data['k']!=='offer') { throw new InvalidArgumentException('Ce choix n’est pas disponible avec ce lien.'); }
    }
    public static function link($request) {
        try {
            $data=self::body($request); $env=self::env($data);$action=$data['action'] ?? '';
            if (!in_array($action,['view','cancel','accept','decline'],true)) { return self::error('Choix invalide.',400); }
            self::verify_link($data['link'] ?? null,$env,$action);
            if ($action!=='view' && ($data['consent'] ?? false)!==true) { return self::error('Confirmez votre choix.',400); }
            unset($data['action']); return self::enqueue($action,$data);
        } catch (Throwable $error) { return self::error('Ce lien est invalide ou a expiré. Aucune action n’a été appliquée.',400); }
    }
    private static function queue_state($env) {
        global $wpdb;
        $table=OpenFabLab_Database::table('relay_actions');
        $row=$wpdb->get_row($wpdb->prepare("SELECT COALESCE(SUM(state='pending' AND expires_at>%d),0) AS pending,COALESCE(SUM(state='processing' AND expires_at>%d),0) AS processing,COALESCE(SUM(state='done' AND result_ok=0),0) AS failed,COALESCE(SUM(state='processing' AND attempts>=3),0) AS retrying FROM $table WHERE environment=%s",time(),time(),$env));
        if ($wpdb->last_error || !$row) { throw new RuntimeException('État de la file indisponible.'); }
        return ['pending'=>(int)$row->pending,'processing'=>(int)$row->processing,'failed'=>(int)$row->failed,'retrying'=>(int)$row->retrying];
    }
    public static function diagnostics() {
        global $wpdb;
        echo '<h2>Connexion OpenFabLab</h2><p>OpenFabLab initie les échanges HTTPS. Aucun accès public au NAS n’est nécessaire.</p>';
        foreach (['production'=>'Normal','test'=>'Test'] as $env=>$label) {
            echo '<h3>'.esc_html($label).'</h3>';
            foreach (['catalogue'=>'Catalogue reçu','poll'=>'Dernière relève des demandes','results'=>'Dernier résultat reçu'] as $key=>$text) {
                $stamp=(int)get_option('openfablab_relay_'.$key.'_'.$env,0);
                echo '<p>'.esc_html($text).' : '.($stamp?esc_html(gmdate('d/m/Y H:i:s',$stamp).' UTC'):'aucun').'</p>';
            }
            try {
                $catalogue=$wpdb->get_var($wpdb->prepare('SELECT catalogue_json FROM '.OpenFabLab_Database::table('relay_catalogues').' WHERE environment=%s',$env));
                $items=json_decode((string)$catalogue,true);$queue=self::queue_state($env);
                echo '<p>'.esc_html((string)(is_array($items)?count($items):0)).' animation(s) reçue(s) · '.esc_html((string)$queue['pending']).' demande(s) en attente · '.esc_html((string)$queue['processing']).' en traitement · '.esc_html((string)$queue['failed']).' non confirmée(s) · '.esc_html((string)$queue['retrying']).' reprise(s) à vérifier.</p>';
            } catch (Throwable $error) { echo '<p>État de la file à vérifier.</p>'; }
            echo '<p>Un contact signé ne prouve pas qu’une réservation a été confirmée. Le stockage historique ci-dessous ne décide plus des places.</p>';
        }
    }
}
