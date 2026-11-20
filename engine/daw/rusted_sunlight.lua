-- Build the score against measured cue times and real, individually editable takes.
local r = reaper
local dir = assert(({r.get_action_context()})[2]:match("^(.*[/\\])"))
local lib = dofile(dir.."rock_fx.lua")
local amp,fx,display,eq,send = lib.amp,lib.fx,lib.displayed,lib.eq,lib.send

local function build()
  local cfg,regions,events,notes,answers = {},{},{},{},{}
  for line in io.lines(dir.."session.tsv") do
    local c={}
    for token in line:gmatch("[^\t]+") do c[#c+1]=tonumber(token) or token end
    if c[1]=="setting" then cfg[c[2]]=c[3]
    elseif c[1]=="region" then regions[#regions+1]={name=c[2],start=c[3],stop=c[4]}
    elseif c[1]=="item" then events[#events+1]=c
    elseif c[1]=="guitar" then answers[#answers+1]=c
    elseif c[1]=="synth" then notes[#notes+1]=c end
  end
  r.Main_OnCommand(40859,0)
  local proj=assert(r.EnumProjects(-1))
  assert(r.CountTracks(proj)==0)
  r.SetCurrentBPM(proj,cfg.bpm,false)
  for _,s in ipairs(regions) do r.AddProjectMarker2(proj,true,s.start,s.stop,s.name,-1,0) end
  local function track(name)
    local i=r.CountTracks(proj)
    r.InsertTrackAtIndex(i,true)
    local t=assert(r.GetTrack(proj,i))
    r.GetSetMediaTrackInfo_String(t,"P_NAME",name,true)
    return t
  end
  local function item(t,name,pos,length,gain,pan,rate)
    local path=dir.."Audio/"..name..".wav"
    local src=assert(r.PCM_Source_CreateFromFile(path),path)
    local it=assert(r.AddMediaItemToTrack(t))
    local take=assert(r.AddTakeToMediaItem(it))
    r.SetMediaItemTake_Source(take,src)
    for key,value in pairs({D_POSITION=pos,D_LENGTH=length,B_LOOPSRC=0,D_FADEINLEN=0,D_FADEOUTLEN=0,D_VOL=amp(gain)}) do
      r.SetMediaItemInfo_Value(it,key,value)
    end
    for key,value in pairs({D_PLAYRATE=rate,B_PPITCH=0,D_PAN=pan}) do r.SetMediaItemTakeInfo_Value(take,key,value) end
    r.GetSetMediaItemTakeInfo_String(take,"P_NAME",name,true)
    return it,take
  end
  local function gain_curve(t,points)
    -- Open an actual volume envelope on this track, respecting REAPER's fader scale.
    r.SetOnlyTrackSelected(t)
    r.Main_OnCommand(40406,0)
    local env=assert(r.GetTrackEnvelopeByName(t,"Volume"))
    r.DeleteEnvelopePointRange(env,-1,cfg.duration+5)
    local mode=r.GetEnvelopeScalingMode(env)
    for _,p in ipairs(points) do
      assert(r.InsertEnvelopePoint(env,p[1],r.ScaleToEnvelopeMode(mode,amp(p[2])),0,0,false,true))
    end
    r.Envelope_SortPoints(env)
  end
  local function cue_curve(t,db)
    local points={{0,db[1]}}
    for i=2,#regions do
      local pos=regions[i].start
      points[#points+1]={pos-.12,db[i-1]}
      points[#points+1]={pos+.04,db[i]}
    end
    gain_curve(t,points)
  end
  local ref=track("YuE2 original · reference (muted)")
  item(ref,"original",0,cfg.duration,0,0,1)
  r.SetMediaTrackInfo_Value(ref,"B_MUTE",1)
  local band={}
  for _,name in ipairs({"drums","bass","guitar","remainder"}) do
    band[name]=track(name.." · "..(name=="remainder" and "original minus three estimates" or "separated estimate"))
    item(band[name],name,0,cfg.duration,0,0,1)
  end
  local lanes={}
  for _,name in ipairs({"pipe","key","motor"}) do lanes[name]=track("Foley · "..name) end
  for _,e in ipairs(events) do item(lanes[e[2]],e[2],e[3],e[4],e[5],e[6],e[7]) end
  local answer=track("Guitar answers · resampled opening")
  for _,e in ipairs(answers) do
    local it,take=item(answer,"guitar",e[2],e[3],e[4],e[5],e[6])
    r.SetMediaItemTakeInfo_Value(take,"D_STARTOFFS",e[7])
    r.SetMediaItemInfo_Value(it,"D_FADEINLEN",.012)
    r.SetMediaItemInfo_Value(it,"D_FADEOUTLEN",.10)
  end
  local synth=track("Solar glass · editable synth answers")
  local synthfx=fx(synth,"ReaSynth")
  for i,val in pairs({[0]=20,[1]=310,[3]=.07,[4]=.36,[5]=-15,[6]=330,[7]=.13,[8]=1200,[9]=-8}) do
    display(synth,synthfx,i,val)
  end
  r.SetMediaTrackInfo_Value(synth,"D_PAN",.28)
  for _,n in ipairs(notes) do
    local it=assert(r.CreateNewMIDIItemInProj(synth,n[2],n[3]+.38,false))
    local take=assert(r.GetActiveTake(it))
    assert(r.MIDI_InsertNote(take,false,false,r.MIDI_GetPPQPosFromProjTime(take,n[2]),
      r.MIDI_GetPPQPosFromProjTime(take,n[3]),0,n[4],n[5],false))
  end
  cue_curve(band.drums,{0,0,0,0,-16,0,0,-4})
  cue_curve(band.guitar,{0,0,0,0,-2,3,0,0})
  local function save(project,pattern,length)
    for k,v in pairs({RENDER_SETTINGS=0,RENDER_BOUNDSFLAG=0,RENDER_STARTPOS=0,RENDER_ENDPOS=length,
      RENDER_TAILFLAG=0,RENDER_SRATE=48000,RENDER_CHANNELS=2}) do r.GetSetProjectInfo(proj,k,v,true) end
    for k,v in pairs({RENDER_FILE="",RENDER_PATTERN=pattern,RENDER_FORMAT="ZXZhdxgAAA=="}) do
      r.GetSetProjectInfo_String(proj,k,v,true)
    end
    r.SetEditCurPos(0,false,false)
    r.Main_SaveProjectEx(proj,dir..project..".RPP",0)
  end
  local master=r.GetMasterTrack(proj)
  r.SetMediaTrackInfo_Value(master,"D_VOL",amp(cfg.trim))
  save("Arrangement","Arrangement",cfg.duration+cfg.tail)
  eq(master,24,310,-.45)
  eq(band.guitar,55,310,-.65,4200,.55)
  local function bus(name,hp,lowmid,cut,levels)
    local t=track(name)
    eq(t,hp,lowmid,cut)
    cue_curve(t,levels)
    return t
  end
  local room=bus("Room · short reflections",180,380,-1,{0,-2,-2,0,-5,-1,0,-3})
  lib.room(room,25,52,7,190,7400)
  send(band.drums,room,-20)
  send(band.guitar,room,-25)
  local haze=bus("Shoegaze · moving late field",280,620,-1.8,{-4,-14,-6,2,-11,-4,3,1})
  lib.room(haze,90,61,41,320,5800)
  local chorus=fx(haze,"JS: sstillwell/chorus_stereo")
  display(haze,chorus,2,.21)
  send(band.guitar,haze,-14)
  send(synth,haze,-11)
  local metal=bus("Metallic space · pipe chamber",470,1250,-1,{-1,-6,-6,-8,2,-8,-4,2})
  lib.room(metal,61,39,17,510,6900)
  send(lanes.pipe,metal,-10)
  send(lanes.key,metal,-17)
  local delay=bus("Delay · guitar answers",320,750,-1,{-8,-10,-6,-8,-12,2,-5,-2})
  local tap=fx(delay,"ReaDelay")
  lib.set(delay,tap,1,0)
  display(delay,tap,0,0)
  display(delay,tap,3,45000/cfg.bpm)
  lib.set(delay,tap,4,0)
  display(delay,tap,5,-12)
  display(delay,tap,6,4300)
  display(delay,tap,7,360)
  send(answer,delay,-10)
  send(answer,haze,-14)
  send(band.guitar,delay,-18)
  send(synth,delay,-16)
  local transition=bus("Transition · reverse motor bloom",550,1700,-1.5,{-5,-7,-3,0,3,-2,-4,1})
  lib.room(transition,74,73,22,600,3900)
  send(lanes.motor,transition,-7)
  save("RUSTED SUNLIGHT","RUSTED SUNLIGHT",cfg.duration+cfg.tail)
  local f=assert(io.open(dir.."fx-state.tsv","w"))
  for n=-1,r.CountTracks(proj)-1 do
    local t=n==-1 and master or r.GetTrack(proj,n)
    local _,name=r.GetTrackName(t)
    for i=0,r.TrackFX_GetCount(t)-1 do
      local _,effect=r.TrackFX_GetFXName(t,i)
      for j=0,r.TrackFX_GetNumParams(t,i)-1 do
        local _,parameter=r.TrackFX_GetParamName(t,i,j)
        local _,value=r.TrackFX_GetFormattedParamValue(t,i,j)
        f:write(name,"\t",effect,"\t",parameter,"\t",value,"\n")
      end
    end
    f:write(name,"\titems\t",r.CountTrackMediaItems(t),"\tenvelopes\t",r.CountTrackEnvelopes(t),"\n")
  end
  f:close()
  return r.GetAppVersion()
end
local ok,message=xpcall(build,debug.traceback)
local f=assert(io.open(dir.."host-status.tmp","w"))
f:write(ok and "BUILT\n" or "ERROR\n",message,"\n")
f:close()
assert(os.rename(dir.."host-status.tmp",dir.."host-status.txt"))
